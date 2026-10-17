#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.1
# summary: >-
#   Standardizes T2 memory frontmatter to the canonical schema and backfills missing fields. 407
#   of 669 files carried no `status`, so 'active' was inferred from ABSENCE — the permissive
#   value — with the reranker's active/terminal split resting on it. Records how each value was
#   obtained and refuses to guess a workstream's lifecycle.
# ---
"""Standardize memory frontmatter.

THE CANONICAL SCHEMA — every T2 memory file carries these five:

    name      the slug (== filename without .md)
    type      feedback | project | reference | user | process
    status    lifecycle, from the vocabulary below
    created   YYYY-MM-DD
    summary   the index row text (what the reranker renders)

Managed by machinery, not by hand: access_count, last_accessed, stability,
importance, pin. Workstream extras (resolves_when, resume_via, close_signal,
cs_section, cs_headline) apply to `project_` files only — see
project_memory-architecture-layers.md §T2 workstream-lifecycle metadata.

STATUS VOCABULARY

    ACTIVE    active         standing knowledge, no workstream lifecycle
              in-flight      being driven now
              handed-off     ball in someone else's court
              follow-on      known cleanup, no external trigger
              unknown        lifecycle genuinely not established  <- see below

    TERMINAL  dormant        self-executing; touch to revive
              archived       resolved, no re-entry context needed
              backlog        aged out to my-lib/backlog/
              superseded_by_<target>
              retracted      the claim was wrong

WHY `unknown` EXISTS. 407 files had no `status` at all, and every consumer read
that absence as "active". That is a two-state probe whose FAILURE case returns
the permissive value — the exact defect class the corpus itself documents in
feedback_probe-must-not-collapse-unknown-into-a-value. Backfilling all 407 to
`active` would have hard-coded the same mistake and made it invisible.

So the backfill asserts `active` ONLY where it is true by construction: a
feedback / reference / user / process memory is standing knowledge and has no
workstream lifecycle to be in. A `project_` file's status is a real fact about
the world that this script cannot observe, so it gets `unknown` and is reported
for triage. `unknown` is treated as ACTIVE by the index (visible, not hidden —
the conservative direction for retrieval) while remaining visibly un-triaged.

Every value this script writes is stamped with its provenance
(`status_source: backfill-YYMMDD`) so a human assertion is never confused with a
script's default.

Usage:
  python3 standardize_memory_frontmatter.py            # report only
  python3 standardize_memory_frontmatter.py --apply
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import memory_dir, TOPIC_PREFIXES  # noqa: E402

MEMORY_DIR = memory_dir().resolve()
LOCK_FILE = MEMORY_DIR / ".access-lock"
STAMP = "backfill-" + datetime.date.today().strftime("%y%m%d")

STANDING_TYPES = ("feedback", "reference", "user", "process")

TERMINAL = ("dormant", "archived", "backlog", "retracted", "obsolete")


def is_terminal(status: str) -> bool:
    s = (status or "").strip().strip("\"'").lower()
    return s.startswith("superseded") or s in TERMINAL


def fm_bounds(text: str) -> tuple[int, int] | None:
    """(start_of_body, end_of_body) char offsets of the frontmatter block."""
    if not text.startswith("---"):
        return None
    nl = text.find("\n")
    if nl == -1:
        return None
    end = text.find("\n---", nl)
    if end == -1:
        return None
    return nl + 1, end + 1


def has_key(fm: str, key: str) -> bool:
    return re.search(rf"^\s*{re.escape(key)}\s*:", fm, re.M) is not None


def insert_keys(text: str, pairs: list[tuple[str, str]]) -> str:
    """Append keys at the END of the frontmatter block, preserving everything else.

    Deliberately does not rewrite the block: 24 files in the corpus fail strict
    YAML, and a round-trip through a parser would silently reformat — or drop —
    content this script has no business touching.
    """
    b = fm_bounds(text)
    if b is None:
        return text
    _, end = b
    add = "".join(f"{k}: {v}\n" for k, v in pairs)
    return text[:end] + add + text[end:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    files = sorted(p for p in MEMORY_DIR.glob("*.md")
                   if p.name.startswith(TOPIC_PREFIXES))
    changes: list[tuple[Path, str, list[tuple[str, str]]]] = []
    stats = Counter()
    triage: list[str] = []

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        b = fm_bounds(text)
        if b is None:
            stats["no_frontmatter"] += 1
            triage.append(f"{path.name}  (no frontmatter at all)")
            continue
        fm = text[b[0]:b[1]]
        slug = path.name[:-3]
        ftype = slug.split("_", 1)[0]
        add: list[tuple[str, str]] = []

        if not has_key(fm, "name"):
            add.append(("name", slug))
            stats["name"] += 1
        if not has_key(fm, "type"):
            add.append(("type", ftype))
            stats["type"] += 1
        if not has_key(fm, "created"):
            ts = datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()
            add.append(("created", ts))
            add.append(("created_source", f"mtime-{STAMP}"))
            stats["created"] += 1
        if not has_key(fm, "summary") and has_key(fm, "description"):
            stats["summary_from_description"] += 1  # reranker already falls back; no write
        if not has_key(fm, "status"):
            if ftype in STANDING_TYPES:
                add.append(("status", "active"))
                stats["status_active"] += 1
            else:
                add.append(("status", "unknown"))
                stats["status_unknown"] += 1
                triage.append(f"{path.name}  (project lifecycle not established)")
            add.append(("status_source", STAMP))
        if add:
            changes.append((path, insert_keys(text, add), add))

    print(f"memory files scanned        : {len(files)}")
    print(f"files needing a backfill    : {len(changes)}")
    for k in ("name", "type", "created", "status_active", "status_unknown",
              "no_frontmatter", "summary_from_description"):
        if stats[k]:
            print(f"   {k:26s} {stats[k]:4d}")
    print()
    print(f"`status: active`  asserted where true by construction (standing knowledge): "
          f"{stats['status_active']}")
    print(f"`status: unknown` where this script MUST NOT guess (project lifecycle) : "
          f"{stats['status_unknown']}")
    if triage:
        print("\nNEEDS HUMAN TRIAGE (these are visible in the index, but un-asserted):")
        for t in triage[:40]:
            print(f"   {t}")
        if len(triage) > 40:
            print(f"   ... and {len(triage)-40} more")

    if not args.apply:
        print("\n(report only — pass --apply to write)")
        return 0

    with open(LOCK_FILE, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for path, content, _ in changes:
            fd, tmp = tempfile.mkstemp(dir=str(MEMORY_DIR), prefix=".fm-tmp-")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp, path)
    print(f"\napplied to {len(changes)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
