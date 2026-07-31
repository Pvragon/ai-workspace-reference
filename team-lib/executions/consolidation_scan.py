#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Deterministic detector for the sleep cycle's consolidation wake (T1->T2 abstraction). Reports ungraduated short-term residue/facts (files in memory/short-term/ older than GRAD_AGE_DAYS still present, i.e. not yet distilled into durable T2 and archived) and weak/stale T2 traces (topic files with access_count 0 and last_accessed far in the past — candidates the passive decay has already pushed Cold). Detection + report only; the graduation act (reading residue -> writing durable T2 -> archiving the residue) is the LLM's job in /dream --consolidate."
# created: 2026-07-12
# last_updated: 2026-07-12
# maintainer: the-operator
# ---
"""
consolidation_scan.py — what needs consolidating (detection only).

Two lists:
  1. ungraduated short-term residue — memory/short-term/*.md older than
     GRAD_AGE_DAYS that are still present (graduation = distilled into a durable
     T2 topic file, then the residue archived to short-term/_archive/). Age is the
     signal: fresh residue is still 'hot'; old residue that never graduated is the
     backlog.
  2. weak/stale T2 traces — topic files with access_count 0 whose last_accessed is
     older than STALE_T2_DAYS. These have already decayed Cold; the scan just makes
     them visible so the consolidation wake can confirm they're still wanted (never
     auto-deletes — that's a human call).

CLI:
  consolidation_scan.py            # human report
  consolidation_scan.py --json     # machine report
"""

import argparse
import datetime
import json
import re
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

MEMORY_DIR = memory_dir()
SHORTTERM = shortterm_dir()
GRAD_AGE_DAYS = 7
STALE_T2_DAYS = 120


def _age_days(mtime: float) -> float:
    return (datetime.datetime.now().timestamp() - mtime) / 86400.0


def scan() -> dict:
    now = datetime.datetime.now().timestamp()
    ungraduated = []
    if SHORTTERM.is_dir():
        for p in sorted(SHORTTERM.glob("*.md")):
            if p.name == "README.md":
                continue
            age = _age_days(p.stat().st_mtime)
            if age > GRAD_AGE_DAYS:
                ungraduated.append({"file": p.name, "age_days": round(age, 1),
                                    "kind": "residue" if "residue" in p.name else "facts"})

    weak = []
    for p in sorted(MEMORY_DIR.glob("*.md")):
        if not p.name.startswith(TOPIC_PREFIXES):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        ac = re.search(r"^access_count:\s*(\d+)", t, re.M)
        la = re.search(r"^last_accessed:\s*(.+)$", t, re.M)
        access = int(ac.group(1)) if ac else 0
        if access > 0:
            continue
        last = p.stat().st_mtime
        if la:
            try:
                last = datetime.datetime.strptime(la.group(1).strip().strip('"'),
                                                  "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc).timestamp()
            except ValueError:
                pass
        age = (now - last) / 86400.0
        if age > STALE_T2_DAYS:
            weak.append({"file": p.name, "stale_days": round(age)})

    return {"ungraduated_shortterm": ungraduated, "weak_t2_traces": weak}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = scan()
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    ung = res["ungraduated_shortterm"]
    weak = res["weak_t2_traces"]
    if not ung and not weak:
        print("✓ consolidation: nothing due")
        return 0
    if ung:
        print(f"ungraduated short-term residue (>{GRAD_AGE_DAYS}d, distill into T2 then archive) — {len(ung)}:")
        for u in ung:
            print(f"  • {u['file']}  ({u['age_days']}d, {u['kind']})")
    if weak:
        print(f"\nweak/stale T2 traces (access_count 0, >{STALE_T2_DAYS}d cold — confirm still wanted) — {len(weak)}:")
        for w in weak[:30]:
            print(f"  • {w['file']}  ({w['stale_days']}d)")
        if len(weak) > 30:
            print(f"  … +{len(weak) - 30} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
