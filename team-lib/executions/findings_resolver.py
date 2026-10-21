#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.0
# summary: "Nightly findings resolver. Re-checks each open auto-lane finding against its source,
#   dismisses the ones proven stale, and in live mode applies only whitelisted fix kinds; checks
#   ownership first (current-state In Flight / Just Handed Off, live peer sessions) and keeps its
#   hands off anything owned. Writes a one-line morning readout. Shadow mode by default."
# created: 2026-10-20
# last_updated: 2026-10-20
# maintainer: pvragon
# ---
"""findings_resolver.py — work the auto lane of the findings inbox, overnight, deterministically.

Why: the owner defers most findings to Your Agent's judgment anyway (2026-10-20: "for 80%+ of the
findings I'm going to defer to you to handle anyway... brief verbal readout at most... It's
important you don't step over the line"). Reviewing findings he always delegates spends his
attention for no decision. This resolver handles the share that a deterministic re-check can
settle and leaves a one-line receipt; everything else stays open, in the lane it belongs to.

Lanes come from findings.py (config/findings-lanes.yaml). For each OPEN finding:

  hands-off  never touched. Listed in the readout, nothing else.
  ask        if a STRONG ownership match says a workstream or live session owns it, it moves to
             hands-off (live only). Otherwise, if its kind has a re-check, a stale one is
             dismissed with a note (allowed in shadow too). Never fixed. Counted as "needs you".
  auto       ownership first (strong or weak match -> hands-off, nothing done). Then the kind's
             re-check: stale -> dismissed with a note. Still true -> in live mode a whitelisted
             fix (if the kind has one and no hard-line pattern matches); otherwise an attempt
             is counted. Two attempts on two different nights -> moved to ask. A kind with no
             re-check stays open and is listed as waiting for a session.

Modes: --shadow writes nothing to the inbox except stale dismissals, and logs what live mode
WOULD do (fixes, lane moves, attempts — the attempt counter lives in the resolver's own state
file in shadow). --live does all of it. With neither flag the mode comes from the config, which
is how dream_cycle.py calls it, so the config's `mode:` is the single switch.

Hard lines this script cannot cross, by construction (there is no code path for them): writes to
any outside API, sending messages, deleting files, touching another session's commits (a push is
refused unless every commit ahead of upstream is one of the cycle's own, by subject), pushing the
public reference repo, pushing a repo outside `push_repos`, and pushing at all while
`allow_push` is false. No LLM is called. Exit status is always 0: it runs inside the nightly
cycle, and a resolver that kills the cycle is worse than one that skips a night.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import findings as F  # noqa: E402
from agent_paths import agent_home, memory_dir, state_dir, workspace, TOPIC_PREFIXES  # noqa: E402

EXEC = Path(__file__).resolve().parent
TEAM_LIB = EXEC.parent
LAST_JSON = state_dir() / "findings-resolver-last.json"
LAST_TXT = state_dir() / "findings-resolver-last.txt"
RSTATE = state_dir() / "findings-resolver-state.json"
LOG = agent_home() / "runtime" / "logs" / "findings_resolver.log"
PUBLIC_REPO = workspace() / "projects" / "ai-workspace-reference"
BUSY_MINUTES = 10


# ── small helpers ────────────────────────────────────────────────────────────────────────────

def _sh(cmd, cwd=None, timeout=300):
    """(returncode, stdout, stderr). Never raises."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 99, "", f"{e.__class__.__name__}: {e}"


def _py(script, *args, timeout=300):
    return _sh([sys.executable, str(EXEC / script), *args], timeout=timeout)


def _git(repo, *args, timeout=60):
    return _sh(["git", "-C", str(repo), *args], timeout=timeout)


def _memory_busy() -> bool:
    """Same test as dream_cycle: a memory topic write in the last 10 minutes means a live session."""
    cutoff = time.time() - BUSY_MINUTES * 60
    try:
        return any(p.stat().st_mtime > cutoff for p in memory_dir().glob("*.md")
                   if p.name.startswith(TOPIC_PREFIXES))
    except Exception:
        return True


def _log(lines):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as fh:
            for line in lines:
                fh.write(line.rstrip() + "\n")
    except Exception:
        pass


def _load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(p)


# ── ownership (hands-off) ────────────────────────────────────────────────────────────────────

def _tokens(s: str):
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def owner_terms(cfg: dict) -> list:
    """[(term, strength, owner)] from current-state's owned sections and live peer sessions.

    STRONG: a whole workstream slug, its first two words, a live session's name stem.
    WEAK:   one distinctive word (length >= owner_min_token, not a stopword, has a letter).
    """
    stop = {w.lower() for w in (cfg.get("owner_stopwords") or [])}
    min_tok = int(cfg.get("owner_min_token") or 5)
    sections = tuple(cfg.get("owner_sections") or ("In Flight", "Just Handed Off"))
    out = []

    def weak(words, owner):
        for t in words:
            if len(t) >= min_tok and t not in stop and re.search(r"[a-z]", t):
                out.append((t, "weak", owner))

    def stem_ok(toks):
        return (len(toks) >= 2 and all(len(t) >= 3 for t in toks[:2])
                and any(len(t) >= 5 and t not in stop for t in toks[:2]))

    try:
        text = (memory_dir() / "current-state.md").read_text()
    except Exception:
        text = ""
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].split("<!--")[0].strip()
            continue
        if not current or not current.startswith(sections) or not line.lstrip().startswith("- "):
            continue
        title = (re.search(r"\*\*(.+?)\*\*", line) or [None, ""])[1]
        for link in re.findall(r"\[\[([^\]|#]+)", line):
            slug = re.sub(r"^(project|reference|feedback|user)_", "", link.strip())
            owner = f"current-state {current}: {link.strip()}"
            out.append((slug.lower(), "strong", owner))
            toks = _tokens(slug)
            if stem_ok(toks):
                out.append(("-".join(toks[:2]), "strong", owner))
            weak(toks, owner)
        if title:
            weak(_tokens(title), f"current-state {current}: {title}")

    # Live peer sessions. Their NAMES only: a focus line is free text and matches everything.
    try:
        import session_activity as sa
        roster = _load_json(sa._roster_path(), {})
        status = _load_json(sa.STATUS_PATH, {})
        for sid, entry in (roster.items() if isinstance(roster, dict) else []):
            if not sa._fresh_entry(entry):
                continue
            name = (status.get(sid) or {}).get("name") or ""
            if not name:
                continue
            owner = f"live session {name}"
            toks = _tokens(re.sub(r"^\d{6}-", "", name))
            if stem_ok(toks):
                out.append(("-".join(toks[:2]), "strong", owner))
            weak(toks, owner)
    except Exception:
        pass
    # De-duplicate, strongest first.
    seen, uniq = set(), []
    for t in sorted(out, key=lambda x: x[1] != "strong"):
        if t[0] not in seen:
            seen.add(t[0])
            uniq.append(t)
    return uniq


def ownership(f: dict, terms: list, subject_words: int = 4):
    """(strength, term, owner) of the first match, or None. Strong beats weak.

    Only the finding's SUBJECT is searched: its key plus the first `subject_words` words of its
    text. Shadow night 2026-10-21 matched four findings to owners and all four were wrong, each
    on a word later in the sentence: provenance ("during the 261020 deckwright debrief") or a
    generic noun ("the harness gate", "skill listing").
    """
    words = re.split(r"\s+", (f.get("text") or "").strip())
    hay = f"{f.get('key', '')} {' '.join(words[:subject_words])}".lower()
    hay_dash = re.sub(r"[\s_/]+", "-", hay)
    for term, strength, owner in terms:
        if strength == "strong":
            if term in hay or term in hay_dash:
                return strength, term, owner
        elif re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", hay):
            return strength, term, owner
    return None


# ── re-checks: does the finding still hold? (True = still true, False = stale, None = unknown) ─

class Ctx:
    """Per-run cache, so ten sweep findings run the sweep once."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._cache = {}

    def once(self, key, fn):
        if key not in self._cache:
            try:
                self._cache[key] = fn()
            except Exception as e:
                self._cache[key] = {"_error": f"{e.__class__.__name__}: {e}"}
        return self._cache[key]


def _own_subject(subject: str, cfg: dict) -> bool:
    return any(re.search(p, subject) for p in (cfg.get("own_commit_subjects") or []))


def _ahead(repo: Path):
    """[(sha, subject)] of commits ahead of upstream, or None when there is no upstream."""
    rc, out, _ = _git(repo, "log", "--format=%h%x09%s", "@{u}..HEAD")
    if rc != 0:
        return None
    return [tuple(l.split("\t", 1)) for l in out.splitlines() if "\t" in l]


def chk_unpushed_layer(f, ctx):
    layer = f["key"].split("-", 1)[1] if "-" in f["key"] else ""
    repo = workspace() / layer
    if not (repo / ".git").exists():
        return None, f"no repo at {repo}"
    ahead = _ahead(repo)
    if ahead is None:
        return None, f"{layer} has no upstream"
    own = [c for c in ahead if _own_subject(c[1], ctx.cfg)]
    if not own:
        return False, (f"{layer}: no cycle-made commit is ahead of upstream "
                       f"({len(ahead)} other commit(s) ahead); the bump/regeneration was pushed")
    return True, f"{layer}: {len(own)} cycle-made of {len(ahead)} commit(s) not pushed"


def chk_memory_hygiene(f, ctx):
    rc, out, err = _py("memory_self_check.py", "--json")
    d = json.loads(out)
    hard = sum(len(d[k]) for k in d if k != "dead_wikilink")
    return (hard > 0), f"memory_self_check: {hard} finding(s) besides dead wikilinks"


def chk_consolidation(f, ctx):
    rc, out, _ = _py("consolidation_scan.py", "--json")
    n = len(json.loads(out).get("ungraduated_shortterm", []))
    st = _load_json(state_dir() / "dream-cycle-state.json", {})
    last = (st.get("last_consolidation") or "")[:10]
    if n == 0:
        return False, "consolidation_scan: 0 residue file(s) due"
    if last and last >= f.get("last_seen", ""):
        return False, f"a consolidation wake ran {last}, after the finding was last seen"
    return True, f"{n} residue file(s) due; last consolidation {last or 'never'}"


def chk_layer_drift(f, ctx):
    d = ctx.once("drift", lambda: json.loads(_py("layer_drift_scan.py", "--json", "--severity", "med")[1]))
    if d.get("status") != "ok":
        return None, f"layer_drift_scan error: {str(d.get('error') or d.get('_error'))[:80]}"
    n = d["summary"]["actionable"]
    items = ", ".join(f"{x['tree']}/{x['item']}" for x in d.get("findings", [])[:3])
    return (n > 0), f"layer_drift_scan: {n} actionable" + (f" ({items})" if n else "")


def chk_pack_pins(f, ctx):
    rc, out, _ = _sh(["bash", str(TEAM_LIB / "_admin" / "update_external_pack_pins.sh"), "--check"])
    return (rc != 0), ("pins stale" if rc else "pins current")


def chk_public_unpushed(f, ctx):
    if not (PUBLIC_REPO / ".git").exists():
        return None, "public reference repo not present"
    ahead = _ahead(PUBLIC_REPO)
    if ahead is None:
        return None, "public reference repo has no upstream"
    return (len(ahead) > 0), f"public reference: {len(ahead)} commit(s) not pushed"


def chk_skill_listing(f, ctx):
    import build_skill_overrides as bso
    res = bso.run("installed")
    if res.get("status") != "ok":
        return None, f"build_skill_overrides: {res.get('error')}"
    missing = (res.get("installed") or {}).get("missing") or []
    unlinked = res.get("unlinked") or []
    return bool(missing or unlinked), f"{len(missing)} key(s) not installed, {len(unlinked)} unlinked"


def _sweep(ctx):
    return ctx.once("sweep", lambda: json.loads(_py("sweep_workstreams.py")[1]))


def chk_close_signal(f, ctx):
    n = (_sweep(ctx).get("summary") or {}).get("without_close_signal")
    if n is None:
        return None, "sweep summary unavailable"
    return (n > 0), f"sweep: {n} open workstream(s) without close_signal"


def _chk_sweep_list(listname):
    def chk(f, ctx):
        sw = _sweep(ctx)
        if "_error" in sw:
            return None, f"sweep failed: {sw['_error'][:80]}"
        name = f["key"].split(":", 1)[1] if ":" in f["key"] else ""
        hit = [x for x in (sw.get(listname) or []) if x.get("name") == name]
        return bool(hit), (f"sweep still lists {name} under {listname}" if hit
                           else f"sweep no longer lists {name} under {listname}")
    return chk


def chk_ccusage_version(f, ctx):
    import shutil
    exe = shutil.which("ccusage")
    if not exe:
        return None, "ccusage not on PATH"
    m = re.search(r'^CCUSAGE_PIN\s*=\s*"([^"]+)"', (EXEC / "dream_cycle.py").read_text(), re.M)
    rc, out, _ = _sh([exe, "--version"], timeout=30)
    ver = (out.strip().split() or ["?"])[-1]
    pin = m.group(1) if m else "?"
    return (ver != pin), f"ccusage {ver}, pin {pin}"


def _repo_for_label(label: str) -> Path:
    return workspace() / label if label in ("team-lib", "my-lib") else workspace() / "projects" / label


def chk_census_gap(f, ctx):
    repo = _repo_for_label(f["key"][4:])
    if not repo.is_dir():
        return None, f"no repo at {repo}"
    rc, out, _ = _py("validate_registry.py", "--repo", str(repo), "--frontmatter")
    m = re.search(r"^\s*(\d+)\s+GAP\b", out, re.M)
    if not m:
        return None, "no census line"
    gap = int(m.group(1))
    return (gap > 0), f"census gap {gap} in {repo.name}"


def chk_project_registry_drift(f, ctx):
    repo = _repo_for_label(f["key"][6:])
    if not repo.is_dir():
        return None, f"no repo at {repo}"
    rc, out, _ = _py("version_gate.py", "--reconcile", str(repo), "--dry-run")
    v = json.loads(out)
    notes = [n for n in (v.get("registry_notes") or []) if "DRIFT" in n or "PARSE" in n]
    rc, out, _ = _py("validate_registry.py", "--repo", str(repo))
    notes += [l.strip() for l in out.splitlines() if l.strip().startswith(("FAIL", "  COVERAGE:"))]
    return bool(notes), f"{len(notes)} manifest issue(s) in {repo.name}"


CHECKS = {
    "unpushed-layer": chk_unpushed_layer,
    "memory-hygiene": chk_memory_hygiene,
    "consolidation": chk_consolidation,
    "layer-drift": chk_layer_drift,
    "pack-pins": chk_pack_pins,
    "public-unpushed": chk_public_unpushed,
    "skill-listing": chk_skill_listing,
    "close-signal": chk_close_signal,
    "sweep-attention": _chk_sweep_list("needs_attention"),
    "sweep-status": _chk_sweep_list("unknown_status"),
    "sweep-undateable": _chk_sweep_list("undateable"),
    "ccusage-version": chk_ccusage_version,
    "census-gap": chk_census_gap,
    "project-registry-drift": chk_project_registry_drift,
}


# ── fixes: the whitelist. Each returns (status, detail); status in applied|blocked|failed. ────
# "blocked" means a config switch or a guard said no; it is not counted as a failed attempt.

def fix_unpushed_layer(f, ctx):
    cfg = ctx.cfg
    layer = f["key"].split("-", 1)[1]
    repo = workspace() / layer
    if not cfg.get("allow_push"):
        return "blocked", "allow_push is false"
    if layer not in (cfg.get("push_repos") or []):
        return "blocked", f"{layer} is not in push_repos"
    rc, br, _ = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if br.strip() != "main":
        return "blocked", f"{layer} is on {br.strip()}, not main"
    ahead = _ahead(repo) or []
    foreign = [c for c in ahead if not _own_subject(c[1], cfg)]
    if foreign:
        return "failed", (f"{len(foreign)} session commit(s) ahead of upstream "
                          f"(e.g. {foreign[0][0]} {foreign[0][1][:50]}); not the resolver's to push")
    rc, out, err = _git(repo, "push", timeout=180)
    return ("applied", f"pushed {len(ahead)} cycle commit(s) in {layer}") if rc == 0 else \
           ("failed", f"git push exited {rc}: {err.strip()[:100]}")


def fix_memory_hygiene(f, ctx):
    if _memory_busy():
        return "blocked", "a session wrote memory in the last 10 minutes"
    rc, out, err = _py("memory_self_check.py", "--fix-safe", "--limit", "15")
    return ("applied", "memory_self_check --fix-safe ran") if rc == 0 else \
           ("failed", f"--fix-safe exited {rc}")


def fix_pack_pins(f, ctx):
    rc, out, err = _sh(["bash", str(TEAM_LIB / "_admin" / "update_external_pack_pins.sh")])
    if rc != 0:
        return "failed", f"pin writer exited {rc}"
    # Pathspec commit: only .gitmodules, so a peer session's staged work is never swept in.
    rc, out, err = _git(TEAM_LIB, "commit", "-q", "-m",
                        "chore(findings-resolver): re-pin external skill packs in .gitmodules",
                        "--", ".gitmodules")
    if rc != 0 and "nothing" not in (out + err).lower():
        return "failed", f"commit failed: {err.strip()[:100]}"
    return "applied", "re-pinned .gitmodules and committed (not pushed)"


FIXES = {
    "unpushed-layer": fix_unpushed_layer,
    "memory-hygiene": fix_memory_hygiene,
    "pack-pins": fix_pack_pins,
}


# ── the pass ─────────────────────────────────────────────────────────────────────────────────

def _short(text: str, n: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def run(mode: str | None = None, today: str | None = None, only: str | None = None) -> dict:
    """One resolver pass over the open inbox.

    Args:
        mode: "shadow" | "live" | None (None -> config `mode`, default shadow).
        today: ISO date override (tests).
        only: restrict to one finding id (debugging).

    Returns {"status": "ok", "mode", "readout", "handled", "would", "needs_you", "waiting",
    "hands_off", "errors", "stale_dismissed"} or {"status": "error", "error"}.
    """
    cfg = F.lane_config()
    if not cfg:
        return {"status": "error", "error": "lane config unreadable (config/findings-lanes.yaml)"}
    mode = mode or cfg.get("mode") or "shadow"
    if mode not in ("shadow", "live"):
        return {"status": "error", "error": f"unknown mode {mode!r}"}
    live = mode == "live"
    tday = datetime.date.fromisoformat(today) if today else datetime.date.today()
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    max_attempts = int(cfg.get("max_attempts") or 2)
    hard = cfg.get("hard_line_patterns") or []
    ctx = Ctx(cfg)
    terms = owner_terms(cfg)
    subject_words = int(cfg.get("owner_subject_words") or 4)
    agent_kinds = set(cfg.get("agent_session_kinds") or [])
    rstate = _load_json(RSTATE, {})
    shadow_attempts = rstate.setdefault("shadow_attempts", {})

    store = F._load()
    rows = [f for f in F._open_findings(store, tday) if not only or f["id"] == only]

    # Decisions are computed first (slow checks), mutations applied after a fresh reload, so a
    # finding recorded by another process while the checks ran is not lost.
    dismiss, lane_moves, attempt_marks = {}, {}, []
    rep = {"handled": [], "would": [], "needs_you": [], "waiting": [], "hands_off": [],
           "errors": [], "stale_dismissed": []}
    log = []

    def note(kind, f, action, detail):
        rep[kind].append({"id": f["id"], "source": f["source"], "key": f.get("key", ""),
                          "action": action, "detail": detail, "text": _short(f["text"])})
        log.append(f"{stamp} {mode} {f['id']} {f['source']}/{f.get('key', '')} {action}: {detail}")

    for f in rows:
        lane = F.lane_of(f)
        _, kind = F.classify(f)
        hay = f"{f.get('key', '')} {f.get('text', '')}"

        if lane == "hands-off":
            note("hands_off", f, "skip", f.get("lane_note") or "hands-off lane")
            continue

        own = ownership(f, terms, subject_words)
        if lane == "ask":
            if own and own[0] == "strong" and not f.get("hold"):
                detail = f"owned by {own[2]} (matched '{own[1]}')"
                if live:
                    lane_moves[f["id"]] = ("hands-off", f"resolver {tday}: {detail}")
                    note("hands_off", f, "moved to hands-off", detail)
                else:
                    note("hands_off", f, "would move to hands-off", detail)
                continue
            chk = CHECKS.get(kind)
            if chk:
                try:
                    still, detail = chk(f, ctx)
                except Exception as e:
                    still, detail = None, f"check error {e.__class__.__name__}: {e}"
                if still is False:
                    dismiss[f["id"]] = f"resolver {tday} ({mode}): stale on re-check — {detail}"
                    note("stale_dismissed", f, "dismissed stale", detail)
                    continue
            note("needs_you", f, "ask", kind)
            continue

        # auto lane. Only a STRONG match hands a finding off; a weak one-word match is a hint in
        # the log, and the re-check still runs (2026-10-21 review of the shadow night).
        if own and own[0] == "weak":
            log.append(f"{stamp} {mode} {f['id']} weak owner hint '{own[1]}' ({own[2]}); not acted on")
        if own and own[0] == "strong":
            detail = f"owned by {own[2]} (matched {own[0]} '{own[1]}')"
            if live:
                lane_moves[f["id"]] = ("hands-off", f"resolver {tday}: {detail}")
                note("hands_off", f, "moved to hands-off", detail)
            else:
                note("hands_off", f, "would move to hands-off", detail)
            continue
        chk = CHECKS.get(kind)
        if not chk:
            note("waiting", f, "no deterministic check", f"kind {kind}: needs a session (/findings)")
            continue
        try:
            still, detail = chk(f, ctx)
        except Exception as e:
            still, detail = None, f"check error {e.__class__.__name__}: {e}"
        if still is None:
            note("errors", f, "re-check inconclusive", detail)
            continue
        if still is False:
            dismiss[f["id"]] = f"resolver {tday} ({mode}): stale on re-check — {detail}"
            note("stale_dismissed", f, "dismissed stale", detail)
            continue

        fix = FIXES.get(kind)
        barred = F._any(hard, hay)
        outcome = "failed"
        if fix and barred:
            fix_detail = "a hard-line pattern matches its wording; not fixed"
        elif fix and not live:
            note("would", f, "would fix", f"{kind} ({detail})")
            continue                       # a would-fix is not a failed attempt
        elif fix:
            outcome, fix_detail = fix(f, ctx)
            if outcome == "applied":
                try:
                    still2, detail2 = chk(f, ctx)
                except Exception as e:
                    still2, detail2 = None, f"recheck error {e}"
                if still2 is False:
                    dismiss[f["id"]] = f"resolver {tday} (live): fixed — {fix_detail}; {detail2}"
                    note("handled", f, "fixed", f"{fix_detail}; {detail2}")
                    continue
                outcome, fix_detail = "failed", f"{fix_detail}, but re-check still true: {detail2}"
            elif outcome == "blocked":
                note("waiting", f, "fix blocked", fix_detail)
                continue
        else:
            fix_detail = "no whitelisted fix for this kind"

        # Still true and not fixed: one attempt tonight (dates de-duplicated, so a manual rerun
        # on the same day does not count twice).
        if live:
            dates = sorted(set(f.get("resolver_attempts") or []) | {tday.isoformat()})
            attempt_marks.append((f["id"], dates))
        else:
            dates = sorted(set(shadow_attempts.get(f["id"]) or []) | {tday.isoformat()})
            shadow_attempts[f["id"]] = dates
        if len(dates) >= max_attempts:
            why = f"{len(dates)} nights still true ({detail}); {fix_detail}"
            if kind in agent_kinds:
                # Not the owner's decision: work for a Your Agent session, listed as waiting.
                note("waiting", f, "needs a Your Agent session", why)
            elif live:
                lane_moves[f["id"]] = ("ask", f"resolver {tday}: {why}")
                note("needs_you", f, "moved to ask", why)
            else:
                note("would", f, "would move to ask", why)
        else:
            note("would" if not live else "waiting", f,
                 f"attempt {len(dates)}/{max_attempts}", f"{detail}; {fix_detail}")

    # ── apply mutations on a fresh load ──
    store = F._load()
    by_id = {f["id"]: f for f in store["findings"] if f["status"] in ("open", "escalated")}
    for fid, why in dismiss.items():
        f = by_id.get(fid)
        if f:
            f.update(status="dismissed", closed=tday.isoformat(), note=why, closed_by="resolver")
    for fid, (lane, why) in lane_moves.items():
        F.set_lane(store, fid, lane, "resolver", why)
    for fid, dates in attempt_marks:
        if fid in by_id:
            by_id[fid]["resolver_attempts"] = dates
    if dismiss or lane_moves or attempt_marks:
        F._save(store)
    else:
        try:   # the statusline cache still reflects tonight's lanes
            F.SEGMENT_CACHE.write_text(F._segment(store, tday))
        except Exception:
            pass
    # Forget shadow attempts for findings that are no longer open.
    open_ids = {f["id"] for f in F._open_findings(store, tday)}
    rstate["shadow_attempts"] = {k: v for k, v in shadow_attempts.items() if k in open_ids}
    rstate["last_run"] = stamp
    _write(RSTATE, json.dumps(rstate, indent=2) + "\n")

    # Needs-you = every open ask-lane finding after tonight, not only the ones looked at.
    needs = [f for f in F._open_findings(store, tday) if F.lane_of(f) == "ask"]
    needs.sort(key=lambda f: f["first_seen"])
    readout = _readout(mode, rep, needs)
    result = {"status": "ok", "mode": mode, "date": tday.isoformat(), "ts": stamp,
              "readout": readout, **rep,
              "needs_you_open": [{"id": f["id"], "source": f["source"], "text": _short(f["text"], 160),
                                  "age_days": F._days(f["first_seen"], tday)} for f in needs],
              "owner_terms": len(terms)}
    _write(LAST_JSON, json.dumps(result, indent=2) + "\n")
    _write(LAST_TXT, readout + "\n")
    log.append(f"{stamp} {mode} SUMMARY {readout}")
    _log(log)
    return result


def _readout(mode, rep, needs) -> str:
    """The one line the morning brief quotes. Live: "Handled 4 overnight; 1 needs you: <text>"."""
    stale = len(rep["stale_dismissed"])
    fixed = len(rep["handled"])
    if mode == "live":
        head = f"Handled {fixed + stale} overnight" if fixed + stale else "Nothing handled overnight"
    else:
        would = sum(1 for x in rep["would"] if x["action"] == "would fix")
        head = (f"Shadow: closed {stale} stale, would fix {would}"
                if stale or would else "Shadow: nothing to close or fix")
    if not needs:
        tail = "nothing needs you"
    elif len(needs) == 1:
        tail = f"1 needs you: {_short(needs[0]['text'], 120)}"
    else:
        tail = f"{len(needs)} need you, oldest: {_short(needs[0]['text'], 100)}"
    extra = f" ({len(rep['waiting'])} wait for a session)" if rep["waiting"] else ""
    return f"{head}; {tail}{extra}"


def self_check() -> None:
    """Ownership matching on the four real findings it got wrong on shadow night 2026-10-21."""
    terms = [("deckwright", "strong", "current-state In Flight: project_deckwright"),
             ("long-run-harness-skill", "strong", "current-state Just Handed Off: project_long-run-harness-skill"),
             ("long-run", "strong", "current-state Just Handed Off: project_long-run-harness-skill"),
             ("harness", "weak", "current-state Just Handed Off: project_long-run-harness-skill"),
             ("skill", "weak", "current-state Just Handed Off: project_long-run-harness-skill")]
    # Provenance late in the sentence is not ownership.
    f1 = {"key": "evicted-note-acme-health-unpushed",
          "text": "current-state notes cap evicted 'Unpushed: acme-health-main 1bd62718 (behind claims "
                  "sessions)' during the 261020 deckwright debrief; re-add with [pin] if still true"}
    assert ownership(f1, terms) is None, ownership(f1, terms)
    # Generic nouns are not ownership (and a weak match would not act anyway).
    f2 = {"key": "stale-team-lib", "text": "1 file(s) in team-lib shipped with a body newer than "
          "their version (pushed outside the harness gate); bumped and committed, not pushed."}
    assert ownership(f2, terms) is None, ownership(f2, terms)
    f3 = {"key": "installed-stale", "text": "1 skill(s) are not linked into ~/.claude/skills (long-run)."}
    own3 = ownership(f3, terms)
    assert own3 is None or own3[0] == "weak", own3
    # Positive controls: a workstream named in the subject is a real owner.
    f4 = {"key": "deckwright-build-stalled", "text": "Shift 3 has not reported for 2 hours."}
    assert ownership(f4, terms)[:2] == ("strong", "deckwright")
    f5 = {"key": "x", "text": "Long-run harness skill: certifier never signed off"}
    assert ownership(f5, terms)[0] == "strong"
    print("self-check ok")


def main() -> int:
    ap = argparse.ArgumentParser(description="nightly findings resolver (auto lane)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--shadow", action="store_true", help="dismiss stale only; log what live would do")
    g.add_argument("--live", action="store_true", help="also apply whitelisted fixes and lane moves")
    ap.add_argument("--today", default=None)
    ap.add_argument("--only", default=None, help="one finding id")
    ap.add_argument("--json", action="store_true", help="print the full result")
    ap.add_argument("--self-check", action="store_true", help="assert ownership matching on known cases")
    a = ap.parse_args()
    if a.self_check:
        self_check()
        return 0
    mode = "shadow" if a.shadow else "live" if a.live else None
    try:
        res = run(mode, a.today, a.only)
    except Exception as e:                      # never fail the nightly cycle
        res = {"status": "error", "error": f"{e.__class__.__name__}: {e}"}
    if a.json or res.get("status") != "ok":
        print(json.dumps(res, indent=2))
    else:
        print(res["readout"])
        for k in ("stale_dismissed", "handled", "would", "needs_you", "waiting", "hands_off", "errors"):
            for x in res[k]:
                print(f"  {k:<15} {x['id']}  {x['source']}/{x['key']}  {x['action']}: {_short(x['detail'], 140)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
