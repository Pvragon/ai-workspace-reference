#!/usr/bin/env python3
# ---
# template: execution
# version: 1.2.0
# summary: "Deterministic memory-hygiene linter — a brick of the self-maintenance 'dream cycle'. Detects: MEMORY.md rows pointing at missing files, orphaned topic files, dead [[wikilinks]] (INFO), near-duplicate topic files by slug-stem overlap (INFO, merge candidates), frontmatter gaps, stale short-term/. --fix-safe applies deterministic safe fixes (filename-dictated name/type backfill AND unambiguous dead-link repair — only when exactly one target matches under dash/underscore + prefix normalization), capped at --limit per run. Ambiguous issues left for judgment. Detection exits 0 unless --strict (exit 1 on hard findings; dead-link + near-dup are INFO). Consumed via /self-check + the debrief groom step."
# created: 2026-07-12
# last_updated: 2026-07-12
# maintainer: the-operator
# ---
"""
memory_self_check.py — detect memory-substrate hygiene issues (no mutations).

This is the "pruning/integration detector" arm of the dream-cycle backlog
(260712-memory-system-framework.md, formerly 260711-self-maintenance-heartbeat).
It does the cheap deterministic *detection*; a later gated phase (or an LLM wake)
handles the judgment fixes. Per the design principle: scripts detect, the dreamer
only wakes for what scripts can't decide.

Checks:
  1. missing_file   — MEMORY.md row `| \`x.md\` |` whose file doesn't exist.
  2. orphan_file    — topic file on disk with no row in MEMORY.md (Hot or Cold).
  3. dead_wikilink  — [[slug]] pointing at no `slug.md` in the memory dir.
  4. frontmatter    — topic file missing a `---` block, or missing name/type.
  5. stale_shortterm— newest short-term/*.md older than STALE_SHORTTERM_DAYS.

Usage:
  python3 memory_self_check.py            # human-readable report
  python3 memory_self_check.py --json     # machine-readable report
  python3 memory_self_check.py --strict   # exit 1 if any finding (for CI/gates)

Note: [[wikilinks]] may intentionally point at not-yet-written memories (the
convention treats them as "worth writing later"). Dead links are therefore
reported as INFO, not errors, and never fail --strict on their own.
"""

import argparse
import datetime
import json
import re
import sys
import tempfile
import os
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

MEMORY_DIR = memory_dir().resolve()
MEMORY_MD = MEMORY_DIR / "MEMORY.md"
MEMORY_ARCHIVE = MEMORY_DIR / "MEMORY-archive.md"  # rolled-off Cold overflow; also a valid index
SHORTTERM_DIR = MEMORY_DIR / "short-term"
TOPIC_PREFIXES = ("feedback_", "project_", "reference_", "user_", "process_", "handoff_")
STALE_SHORTTERM_DAYS = 14

# Files that are legitimately in the dir but are not topic files / not indexed.
NON_TOPIC = {"MEMORY.md", "MEMORY-archive.md", "current-state.md", "identity.md"}


def topic_files() -> set:
    return {p.name for p in MEMORY_DIR.glob("*.md") if p.name.startswith(TOPIC_PREFIXES)}


def memory_md_rows(text: str) -> set:
    return set(re.findall(r"^\| `([^`]+\.md)` \|", text, re.M))


def has_frontmatter(text: str) -> bool:
    return text.startswith("---\n") and text.find("\n---", 4) != -1


MEM_PREFIXES = ("feedback_", "project_", "reference_", "user_", "process_", "handoff_")


def _norm(s: str) -> str:
    return s.lower().replace("-", "_")


def _stem(s: str) -> str:
    s = _norm(s)
    for p in MEM_PREFIXES:
        if s.startswith(p):
            return s[len(p):]
    return s


def resolve_link(link: str, slugs: set):
    """Return the unique slug a dead [[link]] most likely meant, else None.
    Matches under dash/underscore unification, then prefix-agnostic on the stem.
    Only returns a target when exactly one candidate exists (never guesses)."""
    nl = _norm(link)
    cands = [s for s in slugs if _norm(s) == nl]
    if len(cands) == 1:
        return cands[0]
    if cands:
        return None  # ambiguous
    st = _stem(link)
    cands = [s for s in slugs if _stem(s) == st]
    return cands[0] if len(cands) == 1 else None


def check() -> dict:
    findings = {"missing_file": [], "orphan_file": [], "dead_wikilink": [],
                "near_duplicate": [], "frontmatter": [], "stale_shortterm": []}

    files = topic_files()
    # A topic file is "indexed" if it appears in EITHER MEMORY.md or the rolled-off
    # MEMORY-archive.md — both are valid index tiers, so union them (else every
    # archived row false-flags as orphan_file / disappears from missing_file checks).
    md_text = MEMORY_MD.read_text(encoding="utf-8") if MEMORY_MD.exists() else ""
    arch_text = MEMORY_ARCHIVE.read_text(encoding="utf-8") if MEMORY_ARCHIVE.exists() else ""
    rows = memory_md_rows(md_text) | memory_md_rows(arch_text)

    # 1. rows pointing at missing files
    for row in sorted(rows):
        if row.startswith(TOPIC_PREFIXES) and row not in files:
            findings["missing_file"].append(row)

    # 2. topic files with no row
    for f in sorted(files):
        if f not in rows:
            findings["orphan_file"].append(f)

    # 3 & 4. per-file frontmatter + wikilink checks
    slugs = {f[:-3] for f in files}
    for f in sorted(files):
        text = (MEMORY_DIR / f).read_text(encoding="utf-8", errors="replace")
        if not has_frontmatter(text):
            findings["frontmatter"].append(f"{f}: no --- frontmatter block")
        else:
            head = text[: text.find("\n---", 4)]
            if not re.search(r"^\s*name:", head, re.M):
                findings["frontmatter"].append(f"{f}: missing name:")
            if not re.search(r"^\s*type:|^\s*template:", head, re.M):
                findings["frontmatter"].append(f"{f}: missing type:/template:")
        for link in re.findall(r"\[\[([a-z0-9_-]+)\]\]", text):
            if link not in slugs:
                findings["dead_wikilink"].append(f"{f} -> [[{link}]]")

    # 5. near-duplicate topic files (slug-stem token overlap >= 0.7) — merge candidates
    stems = {f: set(_stem(f[:-3]).split("_")) for f in files}
    flist = sorted(files)
    for i in range(len(flist)):
        a = flist[i]
        ta = stems[a]
        if not ta:
            continue
        for b in flist[i + 1:]:
            tb = stems[b]
            if not tb:
                continue
            inter = len(ta & tb)
            union = len(ta | tb)
            if union and inter / union >= 0.7 and inter >= 2:
                findings["near_duplicate"].append(f"{a}  ~  {b}  (overlap {inter}/{union})")

    # 6. stale short-term
    if SHORTTERM_DIR.is_dir():
        dated = sorted(SHORTTERM_DIR.glob("*.md"))
        if dated:
            newest = max(p.stat().st_mtime for p in dated)
            age_days = (datetime.datetime.now().timestamp() - newest) / 86400.0
            if age_days > STALE_SHORTTERM_DAYS:
                findings["stale_shortterm"].append(
                    f"newest short-term file is {age_days:.0f}d old (> {STALE_SHORTTERM_DAYS}d)")

    return findings


PREFIX_TO_TYPE = {"feedback_": "feedback", "project_": "project", "reference_": "reference",
                  "user_": "user", "process_": "process", "handoff_": "handoff"}


def _slug_type(fname: str):
    for pre, typ in PREFIX_TO_TYPE.items():
        if fname.startswith(pre):
            return fname[:-3], typ
    return fname[:-3], None


def fix_safe(limit: int) -> list:
    """Apply ONLY unambiguous, deterministic frontmatter backfills — the 'incremental
    groom'. For a topic file whose frontmatter has NO name: key anywhere, insert a
    top-level `name: <slug>`; if it also lacks type:/template:, insert `type: <prefix>`.
    Both are dictated by the filename, so they're reversible and judgment-free. Capped
    at `limit` files per run so debrief diffs stay small and the corpus converges over
    many sessions. Never touches a file that already has a name (even nested). Returns
    a list of applied fixes.
    """
    applied = []
    slugs = {f[:-3] for f in topic_files()}
    for f in sorted(topic_files()):
        if len(applied) >= limit:
            break
        path = MEMORY_DIR / f
        text = path.read_text(encoding="utf-8", errors="replace")
        if not has_frontmatter(text):
            continue  # a missing --- block is NOT a safe auto-fix; leave for judgment
        end = text.find("\n---", 4)
        head = text[4:end + 1]
        rest = text[end + 1:]
        slug, typ = _slug_type(f)
        fixes = []

        # (a) frontmatter backfill (filename-dictated)
        adds = []
        if not re.search(r"^\s*name:", head, re.M):
            adds.append(f"name: {slug}")
        if typ and not re.search(r"^\s*type:|^\s*template:", head, re.M):
            adds.append(f"type: {typ}")
        if adds:
            head = "".join(a + "\n" for a in adds) + head
            fixes.append("+" + ", ".join(adds))

        # (b) dead-link repair — only when the target is UNAMBIGUOUS under normalization
        def _repl(m):
            link = m.group(1)
            if link in slugs:
                return m.group(0)  # live link, leave it
            target = resolve_link(link, slugs)
            if target and target != link:
                fixes.append(f"[[{link}]]→[[{target}]]")
                return f"[[{target}]]"
            return m.group(0)  # dead but ambiguous — leave for judgment
        rest = re.sub(r"\[\[([a-z0-9_-]+)\]\]", _repl, rest)

        if not fixes:
            continue
        new_text = "---\n" + head + rest
        fd, tmp = tempfile.mkstemp(dir=str(MEMORY_DIR), prefix=".groom-tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        os.replace(tmp, path)
        applied.append(f"{f}: {'; '.join(fixes)}")
    return applied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any non-INFO finding exists")
    ap.add_argument("--fix-safe", action="store_true",
                    help="apply deterministic safe fixes: frontmatter backfills (name/type from "
                         "filename) AND unambiguous dead-link repair (only when exactly one "
                         "target matches under dash/underscore + prefix normalization)")
    ap.add_argument("--limit", type=int, default=15,
                    help="max files to groom per --fix-safe run (default 15)")
    args = ap.parse_args()

    if args.fix_safe:
        fixes = fix_safe(args.limit)
        if args.json:
            print(json.dumps({"fixed": fixes}, indent=2))
        else:
            print(f"groom: applied {len(fixes)} safe frontmatter backfill(s)"
                  + (f" (capped at {args.limit})" if len(fixes) == args.limit else ""))
            for fx in fixes:
                print(f"  • {fx}")
        return 0

    findings = check()

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        total = sum(len(v) for v in findings.values())
        if total == 0:
            print("✓ memory hygiene: clean")
        else:
            labels = {
                "missing_file": "MEMORY.md rows pointing at MISSING files",
                "orphan_file": "topic files with NO MEMORY.md row (orphans)",
                "frontmatter": "frontmatter gaps",
                "stale_shortterm": "stale short-term/",
                "near_duplicate": "near-duplicate topic files (INFO — merge candidates)",
                "dead_wikilink": "dead [[wikilinks]] (INFO — may be intentional TODOs)",
            }
            for key in ("missing_file", "orphan_file", "frontmatter", "stale_shortterm", "near_duplicate", "dead_wikilink"):
                items = findings[key]
                if not items:
                    continue
                print(f"\n{labels[key]} — {len(items)}:")
                for it in items[:40]:
                    print(f"  • {it}")
                if len(items) > 40:
                    print(f"  … +{len(items) - 40} more")
            print(f"\nTotal findings: {total} (detection only — no fixes applied)")

    # dead_wikilink + near_duplicate are INFO and do not fail --strict.
    info = {"dead_wikilink", "near_duplicate"}
    hard = sum(len(findings[k]) for k in findings if k not in info)
    if args.strict and hard > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
