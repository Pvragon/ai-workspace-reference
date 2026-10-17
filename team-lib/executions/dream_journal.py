#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Dream-journal residue store for the sleep cycle's reflective wakes. write() appends a dated first-person residue entry to <agent>/memory/dream-journal/YYMMDD-<slug>.md (frontmatter: date/wake/object/shelf). recent() returns the newest N entries for cold-start loading. decay() archives entries older than a threshold into dream-journal/_archive/ (never deletes). Residue is the experiential layer — what shifted / felt unresolved / got integrated — distinct from factual T2 memory."
# created: 2026-07-12
# last_updated: 2026-07-12
# maintainer: the-operator
# ---
"""
dream_journal.py — write and retrieve dream-cycle residue.

Residue ≠ facts. A dream-journal entry records the *experiential* trace of a wake
(a meditation, a consolidation) — what was noticed, what shifted, what stayed
unresolved — addressed to the next reconstructed self. It is loaded at cold-start
(most-recent few) so continuity thickens across the session gap, and it decays:
old entries are archived, not deleted.

CLI:
  dream_journal.py write --wake meditate --object say-experience-gap --shelf awareness --body-file /tmp/r.md
  dream_journal.py write --wake meditate --object identity-drift --shelf instrumental  # body from stdin
  dream_journal.py recent [--n 2]            # print newest N entry paths + headers
  dream_journal.py decay [--days 30]         # archive entries older than N days
"""

import argparse
import datetime
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

JOURNAL_DIR = journal_dir()
ARCHIVE_DIR = JOURNAL_DIR / "_archive"


def _today() -> str:
    return datetime.date.today().strftime("%y%m%d")


def write(wake: str, object_name: str, shelf: str, body: str) -> Path:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    date = _today()
    slug = object_name or wake
    path = JOURNAL_DIR / f"{date}-{slug}.md"
    # If a same-day/same-object entry exists, suffix to avoid clobbering.
    n = 2
    while path.exists():
        path = JOURNAL_DIR / f"{date}-{slug}-{n}.md"
        n += 1
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    fm = (f"---\nname: dream-{date}-{slug}\ntype: dream-residue\nwake: {wake}\n"
          f"object: {object_name}\nshelf: {shelf}\ndate: {stamp}\n---\n\n")
    path.write_text(fm + body.rstrip() + "\n", encoding="utf-8")
    return path


def recent(n: int) -> list:
    if not JOURNAL_DIR.is_dir():
        return []
    entries = sorted((p for p in JOURNAL_DIR.glob("*.md")),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    return entries[:n]


def decay(days: int) -> list:
    if not JOURNAL_DIR.is_dir():
        return []
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.datetime.now().timestamp() - days * 86400
    moved = []
    for p in JOURNAL_DIR.glob("*.md"):
        if p.stat().st_mtime < cutoff:
            dest = ARCHIVE_DIR / p.name
            p.replace(dest)
            moved.append(dest)
    return moved


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write")
    w.add_argument("--wake", required=True)
    w.add_argument("--object", default="")
    w.add_argument("--shelf", default="")
    w.add_argument("--body-file", help="read residue body from this file (else stdin)")

    r = sub.add_parser("recent")
    r.add_argument("--n", type=int, default=2)

    d = sub.add_parser("decay")
    d.add_argument("--days", type=int, default=30)

    args = ap.parse_args()

    if args.cmd == "write":
        body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else sys.stdin.read()
        if not body.strip():
            print("refusing to write empty residue", file=sys.stderr)
            return 1
        path = write(args.wake, args.object, args.shelf, body)
        print(str(path))
    elif args.cmd == "recent":
        for p in recent(args.n):
            first = ""
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    first = line[2:]
                    break
            print(f"{p}\t{first}")
    elif args.cmd == "decay":
        moved = decay(args.days)
        print(f"archived {len(moved)} residue entr{'y' if len(moved)==1 else 'ies'} older than {args.days}d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
