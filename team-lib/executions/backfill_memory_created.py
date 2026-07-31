#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Backfill a `created:` date onto T2 memory topic files that lack one, derived from the file's git birth date (first commit that added it, followed through renames). Needed because the birth-grace band in rerank_memory_index.py keys on `created:` and the field was only present on 46% of the corpus; file mtime is NOT a usable proxy (update_memory_access.py rewrites frontmatter on every touch, so mtime tracks last touch, not birth). Preserves mtime on write, because files with no `last_accessed` field fall back to mtime for scoring."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: the-operator
# ---
"""
backfill_memory_created.py — give every T2 memory file a trustworthy `created:`.

Why git rather than mtime:
  update_memory_access.py rewrites frontmatter whenever a memory is read or
  edited, so mtime is the last-touch time, not the birth time. Measured on the
  live corpus 2026-07-30: mtime claimed 113 files were <=7d old; git said 40.

Precedence:
  1. An existing `created:` in frontmatter always wins (it is authored, and
     validated at 290/295 agreement with git to within a day).
  2. Otherwise the git birth date — the first commit that ADDED the file,
     followed through renames.
  3. A file git cannot date is left alone and reported, never guessed.

Writes preserve mtime (os.utime), because a file with no `last_accessed` field
scores off mtime; bumping it would fake a recent access.

Usage:
  python3 backfill_memory_created.py --dry-run   # report only (default)
  python3 backfill_memory_created.py --apply
  python3 backfill_memory_created.py --sample 5  # show 5 proposed edits in full
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import memory_dir, agent_home, TOPIC_PREFIXES  # noqa: E402

MEMORY_DIR = memory_dir().resolve()
REPO = agent_home().resolve()


def git_birth_date(path: Path) -> str:
    """ISO date (YYYY-MM-DD) of the commit that first added this file, else ''."""
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "log", "--follow", "--diff-filter=A",
             "--format=%aI", "--", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = [ln for ln in r.stdout.strip().split("\n") if ln]
    return lines[-1][:10] if lines else ""


def frontmatter_span(text: str):
    """(start, end) char offsets of the frontmatter body, or None."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    return None if end == -1 else (4, end + 1)


def has_created(text: str) -> bool:
    span = frontmatter_span(text)
    if not span:
        return False
    return re.search(r"^\s*created:\s*\S", text[span[0]:span[1]], re.M) is not None


def insert_created(text: str, date: str) -> str:
    """Insert `created: <date>` as the last line of the frontmatter block."""
    span = frontmatter_span(text)
    if not span:
        raise ValueError("no frontmatter")
    body_end = span[1]
    return text[:body_end] + f"created: {date}\n" + text[body_end:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--sample", type=int, default=0, help="print N proposed edits in full and exit")
    args = ap.parse_args()

    todo, skipped_have, no_fm, undatable = [], 0, [], []
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if not path.name.startswith(TOPIC_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not frontmatter_span(text):
            no_fm.append(path.name)
            continue
        if has_created(text):
            skipped_have += 1
            continue
        date = git_birth_date(path)
        if not date:
            undatable.append(path.name)
            continue
        todo.append((path, date, text))

    print(f"topic files scanned : {skipped_have + len(todo) + len(no_fm) + len(undatable)}")
    print(f"  already have created: {skipped_have}")
    print(f"  to backfill         : {len(todo)}")
    print(f"  no frontmatter      : {len(no_fm)}  {no_fm[:5]}")
    print(f"  git cannot date     : {len(undatable)}  {undatable[:5]}")

    if args.sample:
        for path, date, text in todo[:args.sample]:
            print(f"\n--- {path.name}  ->  created: {date}")
            print("\n".join(insert_created(text, date).split("\n")[:12]))
        return 0

    if not args.apply:
        print("\n(dry run — pass --apply to write)")
        return 0

    written = 0
    for path, date, text in todo:
        st = path.stat()
        path.write_text(insert_created(text, date), encoding="utf-8")
        os.utime(path, (st.st_atime, st.st_mtime))  # keep mtime: it is a scoring input
        written += 1
    print(f"\nbackfilled {written} files (mtime preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
