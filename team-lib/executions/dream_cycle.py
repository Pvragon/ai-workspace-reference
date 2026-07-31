#!/usr/bin/env python3
# ---
# template: execution
# version: 1.2.0
# summary: "Headless driver for the sleep cycle — the durable scheduler's cron target, fired ONCE DAILY (3:47am, the overnight 'sleep' window). Runs the DETERMINISTIC, autonomous, safe passes directly (incremental groom, hygiene detect, consolidation scan, dream-journal decay, memory-index rerank, my-lib/team-lib layer-drift scan) and CUES the one daily metacognitive wake (meditate / consolidate) by recording what's due in a state file + selecting the next meditation object, without spending LLM tokens. Live-session-aware: skips heavier passes if a memory file was touched in the last BUSY_MINUTES. Design principle: this daily sleep is the ONLY clock-scheduled reasoning; all other wakes/reasoning are project/task-triggered (interactive sessions or explicit /schedule routines), never time-polled. Portable to a dedicated always-on machine later. The LLM wake runs via the /dream skill (interactive now; autonomous on the dedicated machine)."
# created: 2026-07-12
# last_updated: 2026-07-30
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
    except Exception:
        log.append("hygiene: (scan skipped)")

    scan = _run("consolidation_scan.py", "--json")
    ungraduated = 0
    try:
        ungraduated = len(json.loads(scan).get("ungraduated_shortterm", []))
    except Exception:
        pass
    log.append(f"consolidation-scan: {ungraduated} residue file(s) due for graduation")

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
        no_sig = len(sw.get("no_close_signal", []))
        openable = len(sw.get("unresolved_open", [])) + len(sw.get("closed_by_signal", []))
        total = no_sig + openable
        pct = (openable * 100 // total) if total else 0
        log.append(f"close-signal-coverage: {no_sig} of {total} open workstream(s) "
                   f"can never auto-close ({pct}% covered)")
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
