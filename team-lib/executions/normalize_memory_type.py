#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "One-shot migration collapsing the three ways a T2 memory file declared its kind (top-level `type:`, `type:` nested under `metadata:`, and `template:`) into a single authoritative top-level `type:` matching the filename prefix. Preserves `template:` where it holds a REAL document-template name (business-context, project-lifecycle, ...) rather than a memory kind — those are a different axis, and a naive collapse would destroy 45 of them. No script reads these fields (all 26 identify memory kind by filename prefix), so this is a consistency fix and the generated index must not move."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: the-operator
# ---
"""
normalize_memory_type.py — one field, one meaning.

A memory's kind was declared three ways across the corpus:
  241 top-level `type:` · 191 `type:` nested under `metadata:` · 192 `template:`

`template:` is the trap. 188 of its uses are a memory-kind alias (feedback,
reference, project, process), but 45 hold a genuine workspace document-template
name (business-context, project-lifecycle, operational-learning, ...). Treating
the field as a pure alias and rewriting it wholesale destroys those 45; treating
it as purely a template name leaves the alias duplication in place. Hence the
value-dependent rule below.

Rules:
  1. top-level `type:` := the filename prefix. Authoritative, and it is what the
     filename already asserts — every script identifies memory kind that way.
  2. nested `type:` under `metadata:` — removed. Same axis, redundant.
  3. `template:` whose value is a memory kind — removed. Redundant alias.
  4. `template:` whose value is anything else — KEPT untouched.

Nothing reads these fields, so the generated index must be byte-identical
afterwards. That is the acceptance test, not an assumption.

Usage:
  python3 normalize_memory_type.py            # dry run
  python3 normalize_memory_type.py --sample 5
  python3 normalize_memory_type.py --apply
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import memory_dir, TOPIC_PREFIXES  # noqa: E402

MEMORY_DIR = memory_dir().resolve()
KINDS = {"feedback", "project", "reference", "user", "process", "handoff"}


def normalize(text: str, kind: str):
    """-> (new_text, actions). Returns the original text when nothing changes."""
    if not text.startswith("---\n"):
        return text, []
    end = text.find("\n---", 4)
    if end == -1:
        return text, []
    head, body = text[:end + 1], text[end + 1:]

    out, actions, skip_indent = [], [], None
    for ln in head.split("\n"):
        if skip_indent is not None:
            if not ln.strip() or (len(ln) - len(ln.lstrip())) > skip_indent:
                continue
            skip_indent = None

        m_type = re.match(r"^(\s*)type:\s*(.*)$", ln)
        m_tpl = re.match(r"^(\s*)template:\s*(.*)$", ln)

        # nested type: -> drop (rule 2). Top-level is rewritten wholesale below.
        if m_type:
            indent, val = m_type.group(1), m_type.group(2).strip().strip('"')
            skip_indent = len(indent)
            actions.append(f"drop {'nested' if indent else 'top-level'} type: {val}")
            continue

        # template: -> drop ONLY when it is a memory-kind alias (rule 3/4)
        if m_tpl:
            indent, val = m_tpl.group(1), m_tpl.group(2).strip().strip('"')
            if val in KINDS:
                skip_indent = len(indent)
                actions.append(f"drop template: {val} (kind alias)")
                continue
            actions.append(f"keep template: {val} (real template)")

        out.append(ln)

    head = "\n".join(out)
    if not head.endswith("\n"):
        head += "\n"
    new = head + f"type: {kind}\n" + body
    actions.append(f"set type: {kind}")
    return new, actions


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sample", type=int, default=0)
    args = ap.parse_args()

    todo, unchanged, kept_templates = [], 0, 0
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if not path.name.startswith(TOPIC_PREFIXES):
            continue
        kind = path.name.split("_", 1)[0]
        text = path.read_text(encoding="utf-8", errors="replace")
        new, actions = normalize(text, kind)
        if new == text:
            unchanged += 1
            continue
        kept_templates += sum(1 for a in actions if a.startswith("keep template"))
        todo.append((path, new, actions))

    print(f"files to normalize        : {len(todo)}")
    print(f"already canonical         : {unchanged}")
    print(f"real templates preserved  : {kept_templates}")

    if args.sample:
        for path, new, actions in todo[:args.sample]:
            print(f"\n--- {path.name}")
            for a in actions:
                print(f"      {a}")
            print("\n".join(new.split("\n")[:14]))
        return 0

    if not args.apply:
        print("\n(dry run — pass --apply to write)")
        return 0

    for path, new, _ in todo:
        st = path.stat()
        path.write_text(new, encoding="utf-8")
        os.utime(path, (st.st_atime, st.st_mtime))
    print(f"\nnormalized {len(todo)} files (mtime preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
