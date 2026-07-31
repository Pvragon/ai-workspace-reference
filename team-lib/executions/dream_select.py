#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Deterministic meditation-object selector for the dream cycle's reflective wake. Reads the agent's meditation library (meditations/*.md), scores each object by cadence_weight * (days_since_last_sat / spacing) with a hard exclusion of the single most-recently-sat object, and prints the winner. Protects the awareness shelf from being crowded out via a floor that guarantees an awareness object is chosen at least every Nth sit. --record <name> stamps last_sat/sit_count after a real sit. Selection is testable and side-effect-free except --record."
# created: 2026-07-12
# last_updated: 2026-07-12
# maintainer: the-operator
# ---
"""
dream_select.py — pick the next meditation object (weighted rotation).

Score = cadence_weight * min(days_since_last_sat, SPACING) / SPACING
  - never-sat objects (last_sat null) score at full weight (days capped at SPACING).
  - the single most-recently-sat object is excluded outright (no immediate repeats).
  - AWARENESS FLOOR: if the awareness shelf hasn't been chosen in the last
    AWARENESS_FLOOR sits, restrict the candidate set to the awareness shelf — so
    the useful instrumental objects can't starve the useless-but-true ones.

CLI:
  dream_select.py                 # print the chosen object name
  dream_select.py --verbose       # print scores for all objects
  dream_select.py --record <name> # stamp last_sat=today, sit_count++ on that object
"""

import argparse
import datetime
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

MED_DIR = meditations_dir()
SPACING = 21.0            # days; days-since-last-sat saturates here
AWARENESS_FLOOR = 3       # force an awareness object if none chosen in this many sits
STATE = MED_DIR / ".select-state"  # newline log of chosen object names (most recent last)


def _load():
    objs = []
    for p in sorted(MED_DIR.glob("*.md")):
        if p.name == "README.md":
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        def g(k, d=""):
            m = re.search(rf"^{k}:\s*(.+)$", t, re.M)
            return m.group(1).strip() if m else d
        objs.append({
            "name": p.stem, "path": p,
            "shelf": g("shelf", "instrumental"),
            "weight": float(g("cadence_weight", "1.0") or 1.0),
            "last_sat": g("last_sat", "null"),
            "sit_count": int(g("sit_count", "0") or 0),
        })
    return objs


def _days_since(last_sat: str) -> float:
    if not last_sat or last_sat == "null":
        return SPACING
    try:
        d = datetime.datetime.strptime(last_sat, "%Y-%m-%d").date()
        return max(0.0, (datetime.date.today() - d).days)
    except ValueError:
        return SPACING


def _recent_shelves(n: int) -> list:
    if not STATE.exists():
        return []
    names = [x for x in STATE.read_text().splitlines() if x.strip()][-n:]
    by_name = {o["name"]: o["shelf"] for o in _load()}
    return [by_name.get(x) for x in names]


def select(verbose: bool = False):
    objs = _load()
    if not objs:
        return None
    last_chosen = None
    if STATE.exists():
        lines = [x for x in STATE.read_text().splitlines() if x.strip()]
        last_chosen = lines[-1] if lines else None

    candidates = [o for o in objs if o["name"] != last_chosen]
    if not candidates:
        candidates = objs

    # Awareness floor: if no awareness sit in the last AWARENESS_FLOOR, force it.
    recent = _recent_shelves(AWARENESS_FLOOR)
    if recent and "awareness" not in recent:
        aware = [o for o in candidates if o["shelf"] == "awareness"]
        if aware:
            candidates = aware

    for o in candidates:
        o["score"] = o["weight"] * min(_days_since(o["last_sat"]), SPACING) / SPACING

    candidates.sort(key=lambda o: o["score"], reverse=True)
    if verbose:
        for o in candidates:
            print(f"{o['score']:.3f}  [{o['shelf'][:4]}]  {o['name']}  (last_sat={o['last_sat']}, n={o['sit_count']})")
    return candidates[0]


def record(name: str) -> None:
    path = MED_DIR / f"{name}.md"
    if not path.exists():
        print(f"no such object: {name}", file=sys.stderr)
        return
    t = path.read_text(encoding="utf-8")
    today = datetime.date.today().strftime("%Y-%m-%d")
    t = re.sub(r"^last_sat:\s*.*$", f"last_sat: {today}", t, count=1, flags=re.M)
    m = re.search(r"^sit_count:\s*(\d+)", t, re.M)
    if m:
        t = re.sub(r"^sit_count:\s*\d+.*$", f"sit_count: {int(m.group(1)) + 1}", t, count=1, flags=re.M)
    path.write_text(t, encoding="utf-8")
    with open(STATE, "a") as fh:
        fh.write(name + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--record", metavar="NAME")
    args = ap.parse_args()
    if args.record:
        record(args.record)
        print(f"recorded sit: {args.record}")
        return 0
    chosen = select(verbose=args.verbose)
    if not chosen:
        print("no meditation objects found", file=sys.stderr)
        return 1
    if args.verbose:
        print(f"\n-> {chosen['name']}")
    else:
        print(chosen["name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
