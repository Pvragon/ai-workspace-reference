#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "PreToolUse advisory on Agent/Workflow spawns: surfaces available memory, live
#   peer count, and the safe worker count at the exact moment a fan-out is about to start.
#   Speaks only when headroom is short. Never blocks."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: your-agent
# ---
"""fanout_load_advisory.py — say the number at the moment of the decision.

The debrief preflight reports machine load, but a debrief is not the only place a fan-out
starts — and the 2026-07-30 freeze involved subagents, Opus subagents, and five Docker
runs, only some of which came through a debrief. This hook covers the rest: it fires on
Agent and Workflow spawns, wherever they originate.

Design rules, each earned:

  It NEVER blocks. Combined load across concurrent sessions is invisible from inside one
  session, so refusing on local numbers would refuse the wrong things. The .wslconfig cap
  is what bounds damage; this just makes the operator's own rule impossible to skip.

  It is SILENT when there is headroom. An advisory that fires on every spawn is one the
  reader learns to skip, and then it protects nothing on the day it matters.

  It fails LOUD, not silent. If the load probe itself breaks, that is reported rather than
  swallowed — a check that quietly stops running looks exactly like a check with nothing
  to say (feedback_scheduled-reminder-must-self-verify-liveness).

Exit code is always 0. Advisory text goes to stderr, matching inject_lens.py.
"""
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    try:
        sys.stdin.read()          # consume the hook payload; we don't need its contents
    except Exception:
        pass

    try:
        out = subprocess.run([sys.executable, str(HERE / "machine_load.py")],
                             capture_output=True, text=True, timeout=15)
        if out.returncode != 0 or not out.stdout.strip():
            raise RuntimeError(out.stderr.strip()[:120] or "no output")
        d = json.loads(out.stdout)
    except Exception as e:
        # Loud, not silent — but still non-blocking.
        print(f"⚠ Fan-out load check UNAVAILABLE ({type(e).__name__}: {e}). "
              f"Run `free -h` and `/who` yourself before spawning 3+ workers.", file=sys.stderr)
        return 0

    n = d.get("safe_parallel_workers", 0)
    verdict = d.get("fanout_verdict", "unknown")

    # Silent when there is real headroom. The whole point is that the one time it speaks,
    # it is worth reading.
    if verdict == "parallel-ok" and n >= 3:
        return 0

    if verdict == "serial-only":
        head = "⚠ LOAD: run subagents ONE AT A TIME — do not fan out."
    elif verdict == "single-worker":
        head = "⚠ LOAD: at most ONE concurrent subagent right now."
    else:
        head = f"⚠ LOAD: at most {n} concurrent subagent(s) right now."

    print(f"{head}\n  {d.get('why','')}\n"
          f"  Advisory only, nothing is blocked. Two whole-machine freezes (2026-07-13, "
          f"2026-07-30) came from fanning out past this.", file=sys.stderr)
    return 0


def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
