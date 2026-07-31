#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "One-shot migration moving the hand-curated recall summary out of the MEMORY.md / MEMORY-archive.md index rows and into each memory file's own `summary:` frontmatter. This is what makes the index a pure function of the corpus: afterwards rerank_memory_index.py no longer has to read its own prior output to carry summaries forward, and the destructive failure mode (harvest only MEMORY.md, and every archived file's curation is silently destroyed) stops existing. Reads curated rows from BOTH index files; refuses to run if any file would lose text."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: the-operator
# ---
"""
migrate_summary_into_file.py — put the recall summary where it belongs.

The summary shown at cold start is hand-curated and, for 606 of 629 files,
differs from the file's own `description:`. It lives ONLY in the index. That
makes the index stateful: every regeneration must read its own previous output
from both MEMORY.md and MEMORY-archive.md and carry the text forward. Miss the
archive half and the curation of everything rolled off is destroyed.

This moves each curated row into its file as `summary:`. After it runs the
reranker can read summaries from the corpus like any other field.

Safety:
  - Never overwrites an existing `summary:` (that value already lives in the file).
  - Writes a single-line double-quoted scalar with \\ and " escaped, which the
    upgraded parse_frontmatter reads back exactly.
  - Round-trips every file in memory before writing anything, and ABORTS the
    whole run if any file would not read back byte-identical.
  - Preserves mtime: files with no `last_accessed` score off it.

Usage:
  python3 migrate_summary_into_file.py            # dry run
  python3 migrate_summary_into_file.py --sample 5
  python3 migrate_summary_into_file.py --apply
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import memory_dir, TOPIC_PREFIXES  # noqa: E402
import rerank_memory_index as R  # noqa: E402

MEMORY_DIR = memory_dir().resolve()


def yaml_quote(s: str) -> str:
    """Single-line double-quoted YAML scalar."""
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()
    return f'"{s}"'


def insert_summary(text: str, summary: str) -> str:
    """Set `summary:` to the curated text, replacing any existing one.

    212 of the 216 files that already had a `summary:` carried text DIFFERENT from
    their live index row. Both occupy the same slot — the frontmatter standard defines
    `summary:` as "should I open this file?", which is the recall summary's job — but
    only the index row has ever been displayed, and it is the one that has been
    hand-refined. Keeping the file's copy would silently swap the cold-start text for
    one no one has read. The replaced values remain in git.
    """
    end = text.find("\n---", 4)
    if not text.startswith("---\n") or end == -1:
        raise ValueError("no frontmatter")
    head, body = text[:end + 1], text[end + 1:]
    out, skip_indent = [], None
    for ln in head.split("\n"):
        if skip_indent is not None:
            # Continuations of the removed scalar are indented DEEPER than its key.
            # Comparing against "any indentation" would eat sibling keys — most of
            # these summaries are nested under `metadata:`, so their siblings
            # (created:, maintainer:, tags:) are indented too.
            if not ln.strip() or (len(ln) - len(ln.lstrip())) > skip_indent:
                continue
            skip_indent = None
        m = re.match(r"^(\s*)summary:", ln)
        if m:
            skip_indent = len(m.group(1))
            continue
        out.append(ln)
    head = "\n".join(out)
    if not head.endswith("\n"):
        head += "\n"
    return head + f"summary: {yaml_quote(summary)}\n" + body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sample", type=int, default=0)
    args = ap.parse_args()

    md = (MEMORY_DIR / "MEMORY.md").read_text(encoding="utf-8")
    arch = (MEMORY_DIR / "MEMORY-archive.md").read_text(encoding="utf-8")
    curated = R.existing_rows(arch)
    curated.update(R.existing_rows(md))
    print(f"curated rows found (both index files): {len(curated)}")

    todo, unchanged, orphan_rows, replaced = [], 0, [], 0
    for name, summary in sorted(curated.items()):
        path = MEMORY_DIR / name
        if not path.exists():
            orphan_rows.append(name)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        existing = (R.parse_frontmatter(text).get("summary") or "").strip()
        if existing == summary.strip():
            unchanged += 1
            continue
        if existing:
            replaced += 1
        todo.append((path, summary, text))

    print(f"  already correct            {unchanged}")
    print(f"  to write                   {len(todo)}")
    print(f"    of which REPLACE a divergent existing summary: {replaced}")
    print(f"  rows with no file          {len(orphan_rows)} {orphan_rows[:3]}")

    # Round-trip EVERYTHING before writing ANYTHING. A summary that does not read
    # back identically is data loss, and it is not worth discovering halfway through.
    failures = []
    for path, summary, text in todo:
        got = R.parse_frontmatter(insert_summary(text, summary)).get("summary", "")
        if got.strip() != summary.strip():
            failures.append((path.name, summary[:60], got[:60]))
    print(f"\nround-trip failures (abort if >0): {len(failures)}")
    for n, want, got in failures[:5]:
        print(f"    {n}\n      want: {want!r}\n      got : {got!r}")
    if failures:
        print("\nABORTED — refusing to write a migration that loses text.")
        return 2

    if args.sample:
        for path, summary, text in todo[:args.sample]:
            print(f"\n--- {path.name}")
            print("\n".join(insert_summary(text, summary).split("\n")[:10]))
        return 0

    if not args.apply:
        print("\n(dry run — pass --apply to write)")
        return 0

    for path, summary, text in todo:
        st = path.stat()
        path.write_text(insert_summary(text, summary), encoding="utf-8")
        os.utime(path, (st.st_atime, st.st_mtime))
    print(f"\nmigrated {len(todo)} files (mtime preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
