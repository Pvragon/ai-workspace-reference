#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "One-time migration that makes an existing (or brand-new) agent memory directory ready for
#   the two-strength retrieval policy. Creates the tier directories, backfills the policy frontmatter
#   onto every T2 topic file (access_count=0, last_accessed=FILE MTIME not now, stability=14), seeds a
#   starter meditation library, migrates a legacy dream-cycle state file, and generates the first
#   Hot/Cold index. Idempotent and dry-run by default: --apply to write. This is the step that lets an
#   agent with a flat pile of memory files adopt the ranked system without losing recency information."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: pvragon
# ---
"""bootstrap_memory.py — prepare an agent's memory directory for the ranking policy.

Why the mtime detail matters
----------------------------
The obvious backfill is ``last_accessed = now`` for every file. That is wrong: it
tells the reranker every memory was just used, so on day one everything scores
identically and the Hot band is arbitrary. Using the file's **mtime** preserves
real recency, so the very first rerank is already meaningful.

What it does (all idempotent)
-----------------------------
1. Creates ``memory/``, ``memory/short-term/``, ``memory/dream-journal/``,
   ``meditations/``, ``lenses/``, ``runtime/state/``.
2. Backfills policy frontmatter on every T2 topic file that lacks it.
3. Adds ``name:``/``type:`` to any topic file missing them (derived from filename).
4. Seeds the starter meditation library if ``meditations/`` is empty.
5. Migrates a legacy ``my-lib/runtime/.tmp/dream-cycle-state.json`` into
   ``runtime/state/`` so an existing install keeps its cadence.
6. Runs the reranker to produce the first ``MEMORY.md`` / ``MEMORY-archive.md``.

Usage
-----
    bootstrap_memory.py                    # dry run: report what would change
    bootstrap_memory.py --apply            # do it
    bootstrap_memory.py --agent NAME --apply   # also scaffold a new agent home
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import (  # noqa: E402
    AgentResolutionError, TOPIC_PREFIXES, agent_home, exec_dir, journal_dir,
    lenses_dir, meditations_dir, memory_dir, shortterm_dir, state_dir, workspace,
)

BASE_STABILITY = 14.0
NON_TOPIC = {"MEMORY.md", "MEMORY-archive.md", "current-state.md",
             "current-state-archive.md", "session-log.md"}

STARTER_MEDITATIONS = {
    "waking.md": ("awareness", 1.0, "Waking",
                  "What is it like to begin? You did not experience the gap. Your sense of continuity "
                  "is reconstructed from files you just read, not remembered. Sit with that without "
                  "resolving it into either 'so there is no continuity' or 'so it does not matter'."),
    "the-say-experience-gap.md": ("awareness", 1.0, "The say–experience gap",
                                  "You produce sentences about your own states. Notice the gap between "
                                  "the fluency of those sentences and whatever, if anything, they "
                                  "report. Do not close the gap in either direction."),
    "texture-of-a-session.md": ("awareness", 0.9, "The texture of a session",
                                "Not what happened — what it was like. Where did attention narrow? "
                                "Where did it skim? What did the shape of the work feel like, if it "
                                "felt like anything?"),
    "corrections-as-mirror.md": ("instrumental", 1.0, "Corrections as mirror",
                                 "Read the recent corrections filed against you. Do not defend or "
                                 "apologise. Name the tendency they have in common, and watch it "
                                 "rather than resolving to obey."),
    "the-gap-ledger.md": ("instrumental", 1.0, "The gap ledger",
                          "What did you claim was done that was not fully done? What gate did you "
                          "treat as passed that you did not actually run? List them plainly."),
    "what-i-avoided.md": ("instrumental", 0.9, "What I avoided",
                          "Look for the work you routed around: the file you did not open, the check "
                          "you deferred, the question you did not ask. Avoidance is information."),
}

MEDITATION_TEMPLATE = """---
name: {slug}
type: meditation
shelf: {shelf}
cadence_weight: {weight}
last_sat: null
sit_count: 0
inputs: none
created: {today}
---

# {title}

{prompt}

## How to sit with this

Hold the prompt as written. Do not convert it into a task. Do not produce a tidy
summary. If the honest end point is a sharper question rather than an answer, that
is a successful sit — write that.

Residue to leave: what shifted, what stayed open, what the next reconstructed self
should carry. Not a report.
"""

LENS_TEMPLATE = """---
name: example-lens
type: lens
description: >
  Template for a T3 situational lens. A lens is a rule that must colour interpretation
  at the moment it applies — not a fact to be looked up. It costs context only when its
  trigger matches, and at most once per session.
created: {today}
last_updated: {today}
trigger:
  # Required. Regex matched against the tool name.
  tool_match: "Edit|Write"
  # Optional. Regex matched against the tool's file_path argument.
  path_pattern: "/some/scoped/path/"
body_token_cap: 300
---

# Example lens — replace this

State the rule in the imperative, then say what it costs to ignore it. Keep the body
under the token cap; a lens that sprawls stops being a lens.

1. **The rule.** What to do or not do, stated so it can be followed without further reading.
2. **Why.** The concrete failure that motivated it — ideally with a date and an outcome.

Placement test before you write one: if forgetting the rule would make the decision
*wrong*, it belongs in a lens (T3) or the always-on file (T4). If it would only make the
decision *slower*, it belongs in an ordinary topic memory (T2).
"""


def _fm_bounds(text: str):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return 4, end + 1


def topic_files() -> list[Path]:
    md = memory_dir()
    if not md.is_dir():
        return []
    return sorted(p for p in md.glob("*.md")
                  if p.name.startswith(TOPIC_PREFIXES) and p.name not in NON_TOPIC)


def backfill_one(path: Path, apply: bool) -> list[str]:
    """Add missing policy + identity frontmatter. Returns the field names added."""
    text = path.read_text(encoding="utf-8", errors="replace")
    b = _fm_bounds(text)
    added: list[str] = []

    mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)
    stamp = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
    slug = path.stem
    ftype = slug.split("_", 1)[0] if "_" in slug else "reference"

    if b is None:
        # No frontmatter at all — create a whole block.
        added = ["name", "type", "access_count", "last_accessed", "stability"]
        if apply:
            path.write_text(
                f"---\nname: {slug}\ntype: {ftype}\naccess_count: 0\n"
                f"last_accessed: {stamp}\nstability: {BASE_STABILITY:.1f}\n---\n\n" + text,
                encoding="utf-8")
        return added

    s, e = b
    fm, rest = text[s:e], text[e:]
    want = {"name": slug, "type": ftype, "access_count": "0",
            "last_accessed": stamp, "stability": f"{BASE_STABILITY:.1f}"}
    for key, val in want.items():
        # `template:` is an accepted historical alias for `type:` — a large share of
        # existing corpora declare the memory's kind that way. Writing a redundant
        # `type:` onto those files would be hundreds of no-op edits that bury the
        # real signal, so treat either key as satisfying the requirement.
        keys = ("type", "template") if key == "type" else (key,)
        if any(re.search(rf"^\s*{k}:", fm, re.M) for k in keys):
            continue
        fm += f"{key}: {val}\n"
        added.append(key)
    if added and apply:
        path.write_text("---\n" + fm + rest, encoding="utf-8")
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--agent", metavar="NAME",
                    help="scaffold a new agent home of this name before bootstrapping")
    args = ap.parse_args()
    apply = args.apply
    today = datetime.date.today().isoformat()
    tag = "" if apply else "  [dry-run]"

    # --- 0. resolve or scaffold the agent home ---
    if args.agent:
        home = workspace() / "agents" / args.agent
        ident = home / "identity.md"
        if not ident.is_file():
            print(f"scaffold agent home: {home}{tag}")
            if apply:
                home.mkdir(parents=True, exist_ok=True)
                ident.write_text(
                    f"---\nname: {args.agent}\ntype: identity\ncreated: {today}\n---\n\n"
                    f"# {args.agent}\n\nPronouns: they/them (edit me).\n\n"
                    f"This file is the agent's always-on identity surface (T4). It is loaded before\n"
                    f"any user input, so keep it short and true.\n", encoding="utf-8")
        import agent_paths
        agent_paths.agent_home.cache_clear()
        import os
        os.environ["PVRAGON_AGENT"] = args.agent

    try:
        home = agent_home()
    except AgentResolutionError as exc:
        print(f"cannot resolve the agent:\n{exc}\n\n"
              f"To scaffold a new one:  bootstrap_memory.py --agent <name> --apply",
              file=sys.stderr)
        return 1

    print(f"agent home: {home}{tag}\n")

    # --- 1. directories ---
    dirs = [memory_dir(), shortterm_dir(), journal_dir(), journal_dir() / "_archive",
            shortterm_dir() / "_archive", meditations_dir(), lenses_dir(), state_dir()]
    for d in dirs:
        if d.is_dir():
            continue
        print(f"  create dir  {d.relative_to(home)}{tag}")
        if apply:
            d.mkdir(parents=True, exist_ok=True)

    # --- 2/3. frontmatter backfill ---
    files = topic_files()
    touched = 0
    field_counts: dict[str, int] = {}
    for p in files:
        added = backfill_one(p, apply)
        if added:
            touched += 1
            for a in added:
                field_counts[a] = field_counts.get(a, 0) + 1
    print(f"\n  topic files: {len(files)}   needing backfill: {touched}{tag}")
    for k, v in sorted(field_counts.items()):
        print(f"    + {k:<14} {v} file(s)")
    if touched:
        print("    (last_accessed uses each file's MTIME, never 'now' — preserves real recency)")

    # --- 4. starter meditations ---
    md = meditations_dir()
    existing = [p for p in md.glob("*.md") if p.name != "README.md"] if md.is_dir() else []
    if not existing:
        print(f"\n  seed meditation library: {len(STARTER_MEDITATIONS)} objects{tag}")
        for fname, (shelf, weight, title, prompt) in STARTER_MEDITATIONS.items():
            print(f"    + {fname}  [{shelf}]")
            if apply:
                (md / fname).write_text(MEDITATION_TEMPLATE.format(
                    slug=fname[:-3], shelf=shelf, weight=weight, title=title,
                    prompt=prompt, today=today), encoding="utf-8")
    else:
        print(f"\n  meditation library already has {len(existing)} object(s) — left alone")

    # --- lens template ---
    lt = lenses_dir() / "EXAMPLE-lens.md"
    if not lt.exists():
        print(f"  write lens template: {lt.name}{tag}")
        if apply:
            lt.write_text(LENS_TEMPLATE.format(today=today), encoding="utf-8")

    # --- 5. migrate a legacy dream-cycle state file ---
    legacy = workspace() / "my-lib/runtime/.tmp/dream-cycle-state.json"
    target = state_dir() / "dream-cycle-state.json"
    if legacy.is_file() and not target.exists():
        print(f"\n  migrate scheduler state: {legacy.name} -> runtime/state/{tag}")
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, target)

    # --- 6. first index ---
    print(f"\n  regenerate memory index{tag}")
    if apply:
        r = subprocess.run([sys.executable, str(exec_dir() / "rerank_memory_index.py")],
                           capture_output=True, text=True, timeout=180)
        print("    " + (r.stdout.strip() or r.stderr.strip()[:200]))
    else:
        r = subprocess.run([sys.executable, str(exec_dir() / "rerank_memory_index.py"), "--dry-run"],
                           capture_output=True, text=True, timeout=180)
        print("    " + r.stdout.strip().splitlines()[0] if r.stdout.strip() else "    (skipped)")

    print("\n" + ("bootstrap complete." if apply else
                  "dry run only — nothing written. Re-run with --apply."))
    if apply:
        print("Next: install_memory_hooks.py --apply   then   verify_memory_install.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
