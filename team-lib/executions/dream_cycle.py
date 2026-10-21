#!/usr/bin/env python3
# ---
# template: execution
# version: 1.7.0
# summary: >-
#   Headless nightly driver for the sleep cycle (03:47 cron). Runs the deterministic, token-free
#   passes — incremental groom, hygiene detect, consolidation scan, journal decay, index rerank
#   — then CUES the one daily metacognitive wake via a state file without spending tokens.
#   Live-session-aware: skips mutating passes if a memory file changed in the last 10 minutes.
# ---
"""
dream_cycle.py — run one dream-cycle tick (deterministic parts + cue reflective parts).

What it does autonomously (safe, no LLM):
  - groom      : memory_self_check.py --fix-safe (deterministic frontmatter backfill)
  - detect     : memory_self_check.py hygiene counts
  - consolidate-scan : consolidation_scan.py (what T1 residue is due for graduation)
  - journal-decay : dream_journal.py decay (archive old residue)
  - rerank     : rerank_memory_index.py (regenerate Hot/Cold)
  - layer-drift: layer_drift_scan.py (is team-lib still current with my-lib?)
  - publication: publish_gate.py --run (regenerate the public layer if it fell behind;
                 the floor under the push hook, which only fires inside this harness)
  - ccusage-prices: one online ccusage call to refresh the price file the statusline
                 reads offline; findings for an off-pin version or unpriced models
  - findings-resolver: findings_resolver.py (mode from config/findings-lanes.yaml, shadow until
                 reviewed): re-check auto-lane findings, dismiss the stale ones, live-mode fixes
                 from a whitelist only; writes the morning readout line
  - skill-listing: build_skill_overrides.py write (regenerate my-lib's skill listing map,
                 commit only those two files, never push); a finding when the INSTALLED map in
                 ~/.claude/settings.json differs or a skill is not linked into the harness

What it CUES (LLM judgment — left for /dream, interactive now, autonomous later):
  - meditate   : if last meditation > MEDITATE_EVERY_HOURS ago, pick the next object
                 (dream_select) and mark meditation_due in the state file.
  - consolidate: if the scan found ungraduated residue, mark consolidate_due.
  - drift      : if the layer scan found actionable divergence, mark drift_due.
                 Resolution is a judgment call (which way does each item go?),
                 so it is cued for a task-triggered session, never auto-applied.

State: <agent_home>/runtime/state/dream-cycle-state.json (last run, due flags, chosen object).
The cue is how the interactive session (or the dedicated machine's autonomous wake)
knows to run the reflective act — the cron never spends tokens on its own.

Coordination: if any memory topic file was modified in the last BUSY_MINUTES, a live
session is likely active; skip groom/rerank (mutating passes) but still scan + cue.

CLI:
  dream_cycle.py                 # one tick (quiet, for cron)
  dream_cycle.py --verbose       # print what it did
  dream_cycle.py --status        # just print the current state file
  dream_cycle.py --record-meditation   # the /dream skill calls this after a sit:
                                 # stamps last_meditation=now, clears meditation_due
  dream_cycle.py --record-consolidation  # ditto for a consolidation wake
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

# --- portable path resolution (team-lib) -------------------------------------
# Scripts here are invoked by absolute path from hooks and cron, so the sibling
# module is not importable from cwd. Add our own directory to sys.path first.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import (  # noqa: E402
    memory_dir, meditations_dir, lenses_dir, journal_dir, shortterm_dir,
    state_dir, exec_dir, backlog_dir, agent_home, workspace, TOPIC_PREFIXES,
)
# -----------------------------------------------------------------------------

EXEC = exec_dir()
MEMORY_DIR = memory_dir()
STATE = state_dir() / "dream-cycle-state.json"

BUSY_MINUTES = 10            # a memory write this recent => a session is likely live
MEDITATE_EVERY_HOURS = 22    # cue at most one meditation per daily sleep (< 24h tick)
GROOM_LIMIT = 15


def _run(script, *args):
    try:
        r = subprocess.run([sys.executable, str(EXEC / script), *args],
                           capture_output=True, text=True, timeout=120)
        return r.stdout.strip()
    except Exception as e:
        return f"(error: {e})"


def _run_sh(script, *args):
    """Same contract as _run, for shell scripts. Never raises: a hygiene pass that
    kills the nightly tick is worse than a hygiene pass that silently no-ops."""
    path = EXEC / script
    if not path.exists():
        return "(not present)"
    try:
        r = subprocess.run(["bash", str(path), *args],
                           capture_output=True, text=True, timeout=300)
        out = (r.stdout or r.stderr).strip().splitlines()
        return out[-1] if out else "ok"
    except Exception as e:
        return f"(error: {e})"


def _finding(source, key, text, severity="normal"):
    """Route an audit observation into the findings inbox instead of a log line.

    Every scan below already ran nightly and every result already became a log.append()
    that nobody read. The pipeline existed and terminated in a file. This is the missing
    last inch: the same observation, in a queue with an ambient counter and a pull.
    Best-effort — a findings failure must never kill the tick.
    """
    try:
        _run("findings.py", "record", "--source", source, "--key", key,
             "--text", text, "--severity", severity)
    except Exception:
        pass


def _findings_resolver() -> str:
    """Run findings_resolver.py with the config's mode; return its readout line. Never raises.

    Its own subprocess (not _run) for the longer timeout: its re-checks include a registry
    validation per repo, which can outlast _run's 120 s.
    """
    try:
        r = subprocess.run([sys.executable, str(EXEC / "findings_resolver.py")],
                           capture_output=True, text=True, timeout=900)
        return ((r.stdout.strip().splitlines() or ["(no output)"])[0])[:200]
    except Exception as e:
        return f"(skipped: {e.__class__.__name__})"


CCUSAGE_PIN = "20.0.30"      # the version team-lib/_admin/statusline.sh is validated against (re-tested 2026-10-19)


def _ccusage_prices() -> str:
    """Refresh ccusage's on-disk price file once a night, and guard its version.

    The statusline runs `ccusage --offline` every minute against ccusage's cached copy of
    LiteLLM's price list (~/.cache/ccusage/http-cache), so renders cost no network. This
    one ONLINE call is what keeps that copy current: a newly released model gets a price
    within a day of LiteLLM listing it. Until then the statusline shows "$?" and logs to
    ~/.claude/ccusage-unpriced.log, which this pass turns into a finding.
    The version guard exists because v18 turned the statusline into a permanent corpus
    parse (>120 s, ~4 GB, never cached) — measured 2026-10-10. Never raises.
    """
    import shutil
    import time
    exe = shutil.which("ccusage")
    if not exe:
        return "skipped (ccusage not on PATH)"
    try:
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=30).stdout.strip().split()[-1]
    except Exception as e:
        return f"(error reading version: {e})"[:120]
    if ver != CCUSAGE_PIN:
        _finding("ccusage", "version",
                 f"ccusage is {ver}; the statusline is validated against {CCUSAGE_PIN}. "
                 f"Re-test the statusline (blocks/daily JSON shape, speed) before re-pinning.")
    today = datetime.date.today().strftime("%Y%m%d")
    try:
        r = subprocess.run([exe, "daily", "--since", today, "--json"],
                           capture_output=True, text=True, timeout=120)
    except Exception as e:
        _finding("ccusage", "price-refresh", f"online price refresh failed: {e}"[:200])
        return f"(error: {e})"[:120]
    if r.returncode != 0:
        _finding("ccusage", "price-refresh",
                 f"online price refresh exited {r.returncode}: {(r.stderr or '').strip()[:150]}")
        return f"refresh exited {r.returncode}"
    unpriced = set()
    log_path = Path.home() / ".claude" / "ccusage-unpriced.log"
    try:
        cutoff = time.time() - 86400
        if log_path.exists() and log_path.stat().st_mtime > cutoff:
            for line in log_path.read_text(errors="ignore").splitlines()[-500:]:
                ts, _, rest = line.partition(" ")
                try:
                    when = datetime.datetime.fromisoformat(ts).timestamp()
                except ValueError:
                    continue
                if when > cutoff and "unpriced model(s):" in rest:
                    unpriced.update(m for m in rest.split(":", 1)[1].strip().split(",") if m)
    except Exception:
        pass
    if unpriced:
        _finding("ccusage", "unpriced-models",
                 f"statusline showed $? in the last 24 h: no price yet for {', '.join(sorted(unpriced))} "
                 f"(waiting on LiteLLM's price file)")
    return f"ok v{ver}, price file checked online" + (f"; unpriced: {', '.join(sorted(unpriced))}"
                                                       if unpriced else "")


def _load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {}


def _save_state(s: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2))


def _session_busy() -> bool:
    cutoff = datetime.datetime.now().timestamp() - BUSY_MINUTES * 60
    for p in MEMORY_DIR.glob("*.md"):
        if p.name.startswith(TOPIC_PREFIXES) and p.stat().st_mtime > cutoff:
            return True
    return False


AGENTS_REPO = agent_home()


def _commit_push(log: list) -> None:
    """Pull-before / commit / push the agents repo — for an autonomous host with no
    debrief to sweep the deterministic changes (groom, rerank, journal decay). Best-
    effort: any git failure is logged, never fatal. Only the agents repo is touched
    (that's what the cycle mutates)."""
    import subprocess as sp
    def git(*a):
        return sp.run(["git", "-C", str(AGENTS_REPO), *a], capture_output=True, text=True, timeout=120)
    try:
        git("pull", "-q", "--no-edit")
        st = git("status", "--porcelain")
        if not st.stdout.strip():
            log.append("commit: nothing to commit")
            return
        git("add", "-A")
        git("commit", "-q", "-m", "dream-cycle: autonomous nightly sleep (deterministic passes)")
        r = git("push", "-q")
        log.append("commit: pushed" if r.returncode == 0 else f"commit: push failed ({r.stderr.strip()[:80]})")
    except Exception as e:
        log.append(f"commit: error ({e})")



def _skill_listing(log: list, repo: Path | None = None, harness: Path | None = None,
                   settings: Path | None = None, finding=None, commit: bool = True) -> dict:
    """Nightly: regenerate my-lib/config/claude-skill-overrides.json, warn if the INSTALLED map differs.

    The map is a rendering of every skill's `listing:` (frontmatter -> sidecars -> defaults). A
    SKILL.md edited and pushed without anyone re-running build_skill_overrides leaves the JSON
    stale, and a stale JSON is the thing the installer installs. So the generated file is
    regenerated here and committed (never pushed) in my-lib — only those two paths, via a pathspec
    commit, so a peer session's staged work is never swept in.

    The INSTALL is deliberately not done here: it writes ~/.claude/settings.json, which is the
    owner's file and prompts in-session. A difference becomes a finding instead, worded so the
    agent runs it with one approval — never a command for the owner to type.
    Returns {"regenerated", "installed_ok", "unlinked"} for the self-check. Never raises.
    """
    out = {"regenerated": False, "installed_ok": None, "unlinked": []}
    finding = finding or _finding
    try:
        sys.path.insert(0, str(EXEC))
        import build_skill_overrides as bso
        repo = repo or (workspace() / "my-lib")
        harness = harness or bso.DEFAULT_HARNESS
        settings = settings or bso.DEFAULT_SETTINGS
        if not (repo / "config").is_dir() or not Path(harness).is_dir():
            log.append("skill-listing: (skipped — no my-lib/config or harness skills dir)")
            return out
        res = bso.run("write", repo, Path(harness), Path(settings))
        if res.get("status") != "ok":
            log.append(f"skill-listing: (error — {res.get('error')})")
            return out
        out["regenerated"] = bool(res.get("wrote"))
        out["unlinked"] = list(res.get("unlinked") or [])
        if out["regenerated"] and commit and (repo / ".git").exists():
            r = subprocess.run(
                ["git", "-C", str(repo), "commit", "-q", "-m",
                 "chore(config): regenerate the skill listing map (dream cycle)", "--",
                 bso.OUT_REL, bso.STATE_REL],
                capture_output=True, text=True, timeout=60)
            log.append("skill-listing: map regenerated and committed" if r.returncode == 0
                       else f"skill-listing: map regenerated, commit failed ({r.stderr.strip()[:80]})")
        else:
            log.append("skill-listing: map " + ("regenerated" if out["regenerated"] else "current")
                       + f" ({len(res['overrides'])} keys)")
        d = bso.installed_diff(res["overrides"], set(res["overrides"]), Path(settings))
        missing, foreign = d.get("missing") or [], d.get("foreign") or []
        out["installed_ok"] = not missing
        if missing or out["unlinked"]:
            parts = []
            if missing:
                parts.append(f"{len(missing)} skill listing key(s) in "
                             f"my-lib/{bso.OUT_REL} are not installed in ~/.claude/settings.json "
                             f"(e.g. {', '.join(map(str, missing[:4]))}). Your Agent runs "
                             f"install_skill_overrides.py --apply (the operator switches auto mode off for "
                             f"one approval), then sessions restart.")
            if out["unlinked"]:
                parts.append(f"{len(out['unlinked'])} skill(s) are not linked into ~/.claude/skills "
                             f"({', '.join(out['unlinked'][:4])}). Your Agent runs link_skills.py (the operator "
                             f"switches auto mode off for one approval).")
            if foreign:
                parts.append(f"{len(foreign)} foreign key(s) set outside the tool are kept.")
            finding("skill-listing", "installed-stale", " ".join(parts))
            log.append(f"skill-listing: installed map differs ({len(missing)} key(s)), "
                       f"{len(out['unlinked'])} unlinked")
    except Exception as e:                                   # a hygiene pass never kills the tick
        log.append(f"skill-listing: (error: {e.__class__.__name__}: {e})")
    return out


def _census(repo_path, label, log, finding):
    """Frontmatter census for one repo — report only, never fix.

    ⚑ Added 2026-08-08 because the census was the one half of registry conformance NOTHING ran on
    a schedule. Manifests and index.md tables self-maintain (push gate + the reconcile above), but
    the gap count — files that carry no `summary:` at all — was measured only when a human typed
    the flag. A number nobody recomputes drifts back up silently, which is the exact failure this
    whole capability exists to prevent. `--frontmatter` exits 1 when the gap is non-zero.

    Report-only in EVERY layer, including the ones we own: adding frontmatter is authorship, not a
    deterministic transform, and a 3am job must not invent a summary. Regenerating an index is a
    transform; writing a sentence about what a file is for is not.
    """
    try:
        r = subprocess.run(
            [sys.executable, str(EXEC / "validate_registry.py"), "--repo", str(repo_path),
             "--frontmatter"],
            capture_output=True, text=True, timeout=300)
    except Exception:
        log.append(f"frontmatter-census[{label}]: (skipped)")
        return
    m = re.search(r"^\s*(\d+)\s+GAP\b(.*)$", r.stdout, re.M)
    if not m:
        log.append(f"frontmatter-census[{label}]: (no census line)")
        return
    gap = int(m.group(1))
    log.append(f"frontmatter-census[{label}]: {gap} file(s) with no summary")
    if gap:
        # ⚑ Only the lines UNDER "gap by directory:" — a bare `\s+\d+\s+\S` also matches the
        # census header rows, so the first version of this put "1651 markdown files" in the
        # finding as if it were a gap location. Anchor to the section, not to the line shape.
        tail = r.stdout.split("gap by directory:", 1)
        dirs = ([l.strip() for l in tail[1].splitlines() if re.match(r"^\s+\d+\s+\S", l)][:6]
                if len(tail) > 1 else [])
        finding("frontmatter-census", f"gap-{label}",
                f"{label} has {gap} agent-consumable file(s) with no `summary:`{m.group(2)}. "
                + ("Top: " + "; ".join(dirs) + ". " if dirs else "")
                + "Either add the frontmatter or DECLARE the tree in "
                  "config/registry-map.yaml `validate.census_exclude` with a reason — an "
                  "exclusion is a deletion decision and must say why. Not fixed here: writing a "
                  "summary is authorship, not a transform a scheduled job may perform.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--commit", action="store_true",
                    help="pull/commit/push the agents repo after the cycle (for autonomous hosts with no debrief)")
    ap.add_argument("--record-meditation", action="store_true",
                    help="record that a meditation wake just happened (stamp last_meditation, clear the due flag)")
    ap.add_argument("--record-consolidation", action="store_true",
                    help="record that a consolidation wake just happened (stamp last_consolidation, clear the due flag)")
    ap.add_argument("--record-drift-review", action="store_true",
                    help="record that a layer-drift review just happened (the team-lib-currency skill "
                         "calls this once it has worked or consciously deferred the findings)")
    args = ap.parse_args()

    state = _load_state()
    if args.status:
        print(json.dumps(state, indent=2))
        return 0

    now = datetime.datetime.now()

    # --- record a completed reflective wake (called by the /dream skill, not cron) ---
    # Without this the cue flags are write-only: nothing ever advanced last_meditation,
    # so meditation_due stayed true forever and the cadence gate never closed.
    if args.record_meditation or args.record_consolidation or args.record_drift_review:
        stamp = now.strftime("%Y-%m-%dT%H:%M:%S")
        if args.record_meditation:
            state["last_meditation"] = stamp
            state["meditation_due"] = False
            state.pop("meditation_object", None)
        if args.record_consolidation:
            state["last_consolidation"] = stamp
            state["consolidate_due"] = False
        if args.record_drift_review:
            state["last_drift_review"] = stamp
            state["drift_due"] = False
        _save_state(state)
        print(json.dumps(state, indent=2))
        return 0

    log = []
    busy = _session_busy()

    # --- deterministic passes ---
    if busy:
        log.append("session appears live (recent memory write) — skipping mutating passes")
    else:
        log.append("groom: " + _run("memory_self_check.py", "--fix-safe", "--limit", str(GROOM_LIMIT)))
        log.append("journal-decay: " + _run("dream_journal.py", "decay", "--days", "30"))

    # scans are read-only — always safe
    check = _run("memory_self_check.py", "--json")
    try:
        d = json.loads(check)
        hard = sum(len(d[k]) for k in d if k != "dead_wikilink")
        log.append(f"hygiene: {hard} finding(s) remain")
        if hard:
            _finding("hygiene", "memory-self-check",
                     f"{hard} memory hygiene finding(s) outstanding (memory_self_check.py)")
    except Exception:
        log.append("hygiene: (scan skipped)")

    scan = _run("consolidation_scan.py", "--json")
    ungraduated = 0
    try:
        ungraduated = len(json.loads(scan).get("ungraduated_shortterm", []))
    except Exception:
        pass
    log.append(f"consolidation-scan: {ungraduated} residue file(s) due for graduation")
    # Fresh residue is the routine path: yesterday's debrief writes it, this tick cues it, and
    # the reflective wake five minutes later graduates it. Recording a finding for that put a
    # permanently open item in the inbox for work that was always done by 03:56 (de4915b21b,
    # open 22 days, 2026-09-24). A finding means the wake FAILED: the flag this tick set last
    # night is still set, because no consolidation wake cleared it.
    if ungraduated and state.get("consolidate_due"):
        _finding("consolidation", "ungraduated-residue",
                 f"{ungraduated} short-term residue file(s) due for graduation into T2, and the "
                 f"last reflective wake did not consolidate (last_consolidation: "
                 f"{state.get('last_consolidation', 'never')})")

    # Layer drift: is the shared library still current with the personal one?
    # Deterministic and read-only, so it belongs in this tick — a linter finds the
    # divergence, a task-triggered session decides what to do about it. Detection
    # here, resolution never here; that is what keeps the daily sleep the only
    # clock-scheduled *reasoning*.
    # Shortcut ledger (execution-standard Key Rule 8): regenerate the generated view of every
    # `shortcut:` code comment, so a deferral cannot quietly become permanent.
    log.append("shortcut-ledger: " + _run("shortcut_ledger.py", "--apply"))

    drift_actionable = 0
    drift_items: list = []
    try:
        d = json.loads(_run("layer_drift_scan.py", "--json", "--severity", "med"))
        if d.get("status") == "ok":
            drift_actionable = d["summary"]["actionable"]
            drift_items = [f"{f['tree']}/{f['item']}" for f in d["findings"]][:10]
        else:
            log.append(f"layer-drift: scan error ({d.get('error', '')[:60]})")
    except Exception:
        log.append("layer-drift: (scan skipped)")
    else:
        log.append(f"layer-drift: {drift_actionable} actionable finding(s)")
        if drift_actionable:
            _finding("layer-drift", "actionable",
                     f"{drift_actionable} actionable my-lib/team-lib drift finding(s): "
                     + ", ".join(drift_items[:4]))

    # External pack pins: a stale pin is invisible on this machine.
    #
    # The gitlink carries the pin for a team install, so bumping a submodule and forgetting
    # to re-run the pin writer changes nothing HERE — it only changes what a public
    # installer fetches, which is a surface nobody on the team ever looks at.
    try:
        import subprocess
        pins = subprocess.run(["bash", str(Path(EXEC).parent / "_admin" / "update_external_pack_pins.sh"),
                               "--check"], capture_output=True, text=True, timeout=60)
        if pins.returncode != 0:
            _finding("publication", "external-pack-pins",
                     "external skill pack pins in .gitmodules are stale — public installs "
                     "would fetch a different commit than this machine has: "
                     + (pins.stdout.strip().splitlines() or ["?"])[-1].strip())
            log.append("external-pack-pins: STALE")
        else:
            log.append("external-pack-pins: current")
    except Exception:
        log.append("external-pack-pins: (check skipped)")

    # Version reconciliation: the floor under the push gate.
    #
    # version_gate is a PreToolUse hook, so it only sees pushes made through this
    # harness. A push from a plain terminal, another machine, or another agent
    # ships unversioned — and unlike publication that cannot be repaired from the
    # outgoing range afterwards, because once pushed `@{u}..HEAD` is empty. Git
    # history still knows, which is what this asks. Commits, never pushes.
    for _layer in ("team-lib", "my-lib"):
        _repo = workspace() / _layer
        if not (_repo / ".git").exists():
            continue
        try:
            v = json.loads(_run("version_gate.py", "--reconcile", str(_repo)))
        except Exception:
            log.append(f"version-reconcile[{_layer}]: (skipped)")
            continue
        n = len(v.get("bumped") or [])
        log.append(f"version-reconcile[{_layer}]: {n} file(s) bumped")
        if n:
            _finding("version-reconcile", f"stale-{_layer}",
                     f"{n} file(s) in {_layer} shipped with a body newer than their "
                     f"version (pushed outside the harness gate); bumped and committed, "
                     f"not pushed.")
        if v.get("registry_rewritten"):
            log.append(f"registry-reconcile[{_layer}]: manifests regenerated")
            _finding("registry-reconcile", f"stale-{_layer}",
                     f"{_layer}'s generated manifests had drifted from the frontmatter they "
                     f"index; regenerated and committed, not pushed. "
                     + " ".join(v.get("registry_notes") or []))
        _census(_repo, _layer, log, _finding)

    _skill_listing(log)

    # Registry drift in PROJECT repos: report, never rewrite.
    #
    # The push gate only sees pushes made through this harness, and a manifest edited straight on
    # main never passes it at all — so without a backstop the index is true exactly when someone
    # happened to use the gated path. This is that backstop. It runs --dry-run deliberately:
    # project repos carry live branches and worktrees belonging to other sessions, and a 3am job
    # that rewrote a manifest in someone's checkout would be fixing the index by corrupting the
    # working state around it. Detection everywhere, mutation only in the layers we own.
    _projects = workspace() / "projects"
    if _projects.is_dir():
        for _proj in sorted(p for p in _projects.iterdir() if (p / "registry").is_dir()):
            try:
                v = json.loads(_run("version_gate.py", "--reconcile", str(_proj), "--dry-run"))
            except Exception:
                log.append(f"registry-reconcile[{_proj.name}]: (skipped)")
                continue
            notes = [n for n in (v.get("registry_notes") or []) if "DRIFT" in n or "PARSE" in n]
            # The generate half only speaks for manifests a registry-map declares derivable. The
            # rest — sections, buckets, exclusion reasons — are VALIDATED, and without this the
            # nightly would report a repo as fine having checked only the half it can rebuild.
            try:
                vr = subprocess.run(
                    [sys.executable, str(EXEC / "validate_registry.py"), "--repo", str(_proj)],
                    capture_output=True, text=True, timeout=300)
                notes += [l.strip() for l in vr.stdout.splitlines()
                          if l.strip().startswith(("FAIL", "  COVERAGE:"))][:8]
            except Exception:
                log.append(f"registry-validate[{_proj.name}]: (skipped)")
            _census(_proj, _proj.name, log, _finding)
            nver = len(v.get("bumped") or [])
            log.append(f"registry-reconcile[{_proj.name}]: "
                       f"{len(notes)} manifest issue(s), {nver} version(s) stale")
            if notes:
                _finding("registry-reconcile", f"drift-{_proj.name}",
                         f"{_proj.name}'s registry does not match what is on disk. "
                         + " ".join(n.strip() for n in notes)
                         + " Run /registry-conformance in that repo — not fixed here, because "
                           "rewriting a manifest in a repo with live worktrees is not a "
                           "scheduled job's call.")

    # Publication: regenerate the public reference layer if it has fallen behind.
    #
    # This does not violate "detection here, resolution never here" — the public repo
    # is a GENERATED artifact, so regenerating it is a deterministic transform of
    # team-lib, in the same class as the reranker, not a judgment. The judgment
    # (pushing it to the world) is deliberately not made here.
    #
    # It exists because publish_gate.py only fires on pushes made through this
    # harness. A push from a plain terminal, another machine, or any session without
    # the hook produces no publication at all, and the public layer sits stale until
    # someone happens to run the scan. This is that backstop.
    try:
        p = json.loads(_run("publish_gate.py", "--run", "--quiet"))
    except Exception:
        log.append("publication: (skipped)")
    else:
        if p.get("status") == "refused":
            log.append("publication: REFUSED — a blocked identifier survived generalization")
            _finding("publication", "leak-blocked",
                     "publish refused: a scrubbed identifier survived generalization. "
                     "The public repo was NOT updated — add a generalization rule.",
                     # findings.py accepts only normal|critical. This said "high", argparse
                     # rejected it, _finding swallowed the error, and refusals from 2026-09-24
                     # to 10-15 never reached the inbox (finding 57ddf181c5, fixed 2026-10-19).
                     severity="critical")
        elif p.get("written"):
            log.append(f"publication: regenerated {p['written']} file(s) (committed, not pushed)")
            _finding("publication", "regenerated",
                     f"public reference regenerated from team-lib ({p['written']} file(s)) "
                     "and committed. Review and push when ready.")
        else:
            log.append("publication: public already current")

    # Close-signal coverage: how much of the corpus can the sweep actually close?
    # A workstream with no close_signal is invisible to pathway 1, so the sweep
    # reporting "nothing closed" is mostly evidence that it had nothing to check.
    # Measured 2026-07-30: 55 of 67 open workstreams had none — ~18% coverage.
    # Read-only (no --apply), so it belongs in this tick; backfilling the signals
    # is judgment and stays task-triggered.
    try:
        # No --json flag: the script emits JSON by default and REJECTS unknown args,
        # so passing one silently degraded this to "(scan skipped)".
        sw = json.loads(_run("sweep_workstreams.py"))
        # READ the published summary; do not re-derive it. This block used to compute
        # `no_sig + unresolved_open + closed_by_signal`, but those arrays are not a
        # partition — an item with no signal that is also unresolved appears in two of
        # them — so the denominator over-counted and coverage read ~2.5x too high.
        # Fixed at the source 2026-07-30; the sweep now owns the number.
        s = sw.get("summary", {})
        no_sig, total, pct = (s.get("without_close_signal", 0), s.get("open_total", 0),
                              s.get("coverage_pct", 0))
        log.append(f"close-signal-coverage: {no_sig} of {total} open workstream(s) "
                   f"can never auto-close ({pct}% covered)")
        if no_sig:
            _finding("close-signal", "untriaged",
                     f"{no_sig} of {total} open workstreams have no close_signal — "
                     f"the sweep cannot ever close them")
        for x in sw.get("needs_attention", []):
            _finding("sweep", f"attention:{x['name']}", f"{x['name']}: {x['detail']}")
        for x in sw.get("unknown_status", []):
            _finding("sweep", f"status:{x['name']}",
                     f"{x['name']} has status '{x['status']}' — invisible to every pathway")
        for x in sw.get("undateable", []):
            _finding("sweep", f"undateable:{x['name']}",
                     f"{x['name']} has no usable date — dormancy can never reach it")
    except Exception as e:
        log.append(f"close-signal-coverage: (scan skipped: {str(e)[:50]})")

    # Transcript corpus: ccusage re-parses EVERY live JSONL on each statusline
    # refresh, so an unbounded corpus is a freeze mechanism, not a tidiness issue.
    # The archiver self-throttles to once/24h and MOVES rather than deletes, so it
    # is safe to call unconditionally — but log the size either way, because the
    # number is the early warning and nothing else reports it.
    # Report BOTH halves. The archiver globs *.jsonl only, so the second number is
    # the one nothing is bounding: `tool-results/*.txt` spill files (a tool output too
    # large to inline gets written to disk and left there) plus stray json/jpg. Measured
    # 2026-07-30: 0.54 GB of JSONL against 1.20 GB of un-archived residue in 8,428
    # files, individual spills up to 64 MB. Growth there is invisible to every existing
    # hygiene pass.
    try:
        proj = Path.home() / ".claude" / "projects"
        jsonl = other = 0
        for f in proj.rglob("*"):
            if not f.is_file():
                continue
            sz = f.stat().st_size
            if f.suffix == ".jsonl":
                jsonl += sz
            else:
                other += sz
        log.append(f"transcript-corpus: {jsonl / 1073741824:.2f} GB jsonl (archived) + "
                   f"{other / 1073741824:.2f} GB tool-results/other (NOT archived)")
    except Exception:
        log.append("transcript-corpus: (size check skipped)")
    if not busy:
        log.append("transcript-archive: " + _run_sh("archive_old_transcripts.sh"))
    # Cheap (~2 s) and read-only for memory, so it runs even when a session is live.
    log.append("ccusage-prices: " + _ccusage_prices())

    if not busy:
        log.append("rerank: " + _run("rerank_memory_index.py"))
        # Findings hygiene runs AFTER every record above, so a condition that stopped

        # being detected tonight closes tonight rather than lingering as queue debt.
        log.append("findings: " + _run("findings.py", "sweep"))

    # Findings resolver: work the auto lane of the inbox, AFTER every record and the sweep above.
    #
    # Re-checks each open auto-lane finding against its source and dismisses the ones proven
    # stale; in live mode also applies the whitelisted fix kinds. It keeps its hands off anything
    # an open workstream or live session owns, and writes the one-line morning readout
    # (runtime/state/findings-resolver-last.txt). No flag on purpose: the mode comes from
    # config/findings-lanes.yaml (`mode: shadow` until the shadow week is reviewed), so that file
    # is the single switch. Runs even when a session is live: shadow writes only stale dismissals
    # to the inbox, and live mode's memory fix has its own busy guard. Never fails the tick.
    log.append("findings-resolver: " + _findings_resolver())

    # --- cue the reflective (LLM) wakes ---
    last_med = state.get("last_meditation")
    med_due = True
    if last_med:
        try:
            dt = datetime.datetime.strptime(last_med, "%Y-%m-%dT%H:%M:%S")
            med_due = (now - dt).total_seconds() >= MEDITATE_EVERY_HOURS * 3600
        except Exception:
            pass
    chosen = None
    if med_due:
        chosen = _run("dream_select.py")
        state["meditation_due"] = True
        state["meditation_object"] = chosen
        log.append(f"CUE meditation_due -> object: {chosen}")
    else:
        log.append("meditation not due yet")

    state["consolidate_due"] = ungraduated > 0
    if ungraduated:
        log.append("CUE consolidate_due")

    # Cue only — never resolved autonomously. Consumed by the team-lib-audit
    # skill and reported (not acted on) by /dream auto.
    state["drift_due"] = drift_actionable > 0
    state["drift_actionable"] = drift_actionable
    state["drift_items"] = drift_items
    if drift_actionable:
        log.append("CUE drift_due")

    state["last_cycle"] = now.strftime("%Y-%m-%dT%H:%M:%S")
    state["last_cycle_busy"] = busy
    _save_state(state)

    # --- autonomous-host persistence: commit+push the deterministic changes ---
    if args.commit and not busy:
        _commit_push(log)
    elif args.commit and busy:
        log.append("commit: skipped (session live)")

    if args.verbose:
        print(f"dream-cycle tick @ {now:%Y-%m-%d %H:%M}")
        for line in log:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
