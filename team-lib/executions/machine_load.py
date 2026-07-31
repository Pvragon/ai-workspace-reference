#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Single source of truth for the pre-fan-out load check: available memory, load
#   average, live peer sessions, and how many concurrent workers are safe. Used by
#   session-debrief preflight and by the PreToolUse advisory on Agent/Workflow spawns."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: your-agent
# ---
"""machine_load.py — how many concurrent workers is it safe to spawn right now?

feedback_concurrent-load-freeze-260713 says to check `/who` AND `free -h` before running
three or more workers. The machine froze by that mechanism twice (2026-07-13, 2026-07-30).
The second time the rule was current and had been read that same day; `/who` was checked
and `free -h` was not. A safeguard phrased as "remember to check X first" fails at exactly
the moment it applies.

This module is the check. Two callers use it and neither asks a human to run anything:
  - session-debrief preflight, which reports it in the block the operator already reads
  - a PreToolUse advisory on Agent/Workflow spawns, which speaks only when it matters

It NEVER blocks. Combined load across concurrent sessions is not observable from inside
one session — the .wslconfig cap is what bounds the damage. The value here is surfacing
the number at the moment of the decision.

Thresholds are deliberately conservative:
  RESERVE     4096 MB  kept for the OS and the parent session
  PER_WORKER  2048 MB  budgeted per subagent
  PER_PEER    2048 MB  reserved for EACH live peer, whose own fan-out we cannot see
  HARD_CAP       3     never more, per reference_wsl-subagent-fanout-disk-thrash
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

RESERVE_MB = 4096
PER_WORKER_MB = 2048
PER_PEER_MB = 2048
HARD_CAP = 3
UNKNOWN_PEERS_ASSUMED = 2


def read_mem():
    """Available MB and total MB from /proc/meminfo (MemAvailable is the honest figure)."""
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        m = re.match(r"(\w+):\s+(\d+) kB", line)
        if m:
            info[m.group(1)] = int(m.group(2)) // 1024
    return info.get("MemAvailable", 0), info.get("MemTotal", 0)


def read_load():
    load1 = float(Path("/proc/loadavg").read_text().split()[0])
    try:
        cpus = int(subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip())
    except Exception:
        cpus = 1
    return load1, cpus


def count_peers():
    """Live peer sessions EXCLUDING us, or -1 when the roster cannot be read.

    -1 is not 0. A lookup that fails toward the most permissive answer launders an
    unknown into a reassurance — which is how the first version of this check silently
    reported "no peers" on a machine running three sessions.
    """
    here = Path(__file__).resolve().parent
    # team-lib first: the coordination layer graduated there on 2026-07-30 and the my-lib
    # copy was deleted in the same commit. The my-lib path stays as a fallback for an
    # install that has not taken that graduation yet.
    for cand in (here / "session_activity.py",
                 here.parent.parent / "my-lib/executions/session_activity.py"):
        if cand.is_file():
            try:
                out = subprocess.run([sys.executable, str(cand), "roster"],
                                     capture_output=True, text=True, timeout=10)
                if out.returncode == 0:
                    n = sum(1 for line in out.stdout.splitlines() if " live " in line)
                    return max(0, n - 1)
            except Exception:
                pass
    return -1


def assess(avail_mb=None, load1=None, cpus=None, peers=None):
    if avail_mb is None or None in (load1, cpus):
        _avail, total = read_mem()
        avail_mb = _avail if avail_mb is None else avail_mb
        _l, _c = read_load()
        load1 = _l if load1 is None else load1
        cpus = _c if cpus is None else cpus
    else:
        total = read_mem()[1]
    if peers is None:
        peers = count_peers()
    unknown = peers < 0
    eff_peers = UNKNOWN_PEERS_ASSUMED if unknown else peers
    budget = avail_mb - RESERVE_MB - PER_PEER_MB * eff_peers
    workers = max(0, min(HARD_CAP, budget // PER_WORKER_MB))
    reason = (f"{avail_mb}MB available, "
              f"{'peer count UNKNOWN (assuming %d)' % UNKNOWN_PEERS_ASSUMED if unknown else f'{peers} live peer(s)'}, "
              f"load {load1:.2f} across {cpus} cpu")
    if load1 > cpus:
        workers = 0
        reason += " — load exceeds cpu count"
    verdict = "parallel-ok" if workers >= 2 else ("single-worker" if workers == 1 else "serial-only")
    return {"mem_available_mb": avail_mb, "mem_total_mb": total, "load_1min": round(load1, 2),
            "cpus": cpus, "live_peer_sessions": peers, "safe_parallel_workers": int(workers),
            "fanout_verdict": verdict, "why": reason}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit the assessment as JSON")
    ap.add_argument("--avail", type=int, help="override available MB (testing)")
    ap.add_argument("--load", type=float, help="override 1-min load (testing)")
    ap.add_argument("--cpus", type=int, help="override cpu count (testing)")
    ap.add_argument("--peers", type=int, help="override peer count; -1 = unknown (testing)")
    a = ap.parse_args()
    r = assess(a.avail, a.load, a.cpus, a.peers)
    if a.json or True:
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
