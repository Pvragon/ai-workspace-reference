#!/usr/bin/env python3
# ---
# template: execution
# version: 1.3.3
# summary: "Headless driver for the sleep cycle — the durable scheduler's cron target, fired ONCE DAILY (3:47am, the overnight 'sleep' window). Runs the DETERMINISTIC, autonomous, safe passes directly (incremental groom, hygiene detect, consolidation scan, dream-journal decay, memory-index rerank, my-lib/team-lib layer-drift scan, public-layer republication) and CUES the one daily metacognitive wake (meditate / consolidate) by recording what's due in a state file + selecting the next meditation object, without spending LLM tokens. Live-session-aware: skips heavier passes if a memory file was touched in the last BUSY_MINUTES. Design principle: this daily sleep is the ONLY clock-scheduled reasoning; all other wakes/reasoning are project/task-triggered (interactive sessions or explicit /schedule routines), never time-polled. Portable to a dedicated always-on machine later. The LLM wake runs via the /dream skill (interactive now; autonomous on the dedicated machine)."
# created: 2026-07-12
# last_updated: 2026-08-01
# maintainer: the-operator
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

import argparse
import datetime
import json
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
    if ungraduated:
        _finding("consolidation", "ungraduated-residue",
                 f"{ungraduated} short-term residue file(s) due for graduation into T2")

    # Layer drift: is the shared library still current with the personal one?
    # Deterministic and read-only, so it belongs in this tick — a linter finds the
    # divergence, a task-triggered session decides what to do about it. Detection
    # here, resolution never here; that is what keeps the daily sleep the only
    # clock-scheduled *reasoning*.
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
                     severity="high")
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

    if not busy:
        log.append("rerank: " + _run("rerank_memory_index.py"))
        # Findings hygiene runs AFTER every record above, so a condition that stopped

        # being detected tonight closes tonight rather than lingering as queue debt.
        log.append("findings: " + _run("findings.py", "sweep"))

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
