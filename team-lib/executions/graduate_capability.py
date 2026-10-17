#!/usr/bin/env python3
# ---
# template: execution
# version: 2.1.1
# summary: >-
#   Graduates a capability from the personal layer to the shared one as a MOVE, not a copy.
#   Skills move and are symlinked back; executions and directives move and the personal copy is
#   archived behind a pointer. Pre-flight refuses a split capability, operator identifiers,
#   personal-code dependencies, and a skill without a valid `listing:` / `category:`.
# ---
"""graduate_capability.py — move a proven capability into the shared library.

Why this replaces graduate_files.py v1.0.0
------------------------------------------
That script sat unused for five months, and neither real graduation in July 2026
invoked it. Not neglect — it could not do the job:

  * it handled FILES ONLY, and every skill is a directory, so it failed on the
    most common case outright;
  * it opened a branch and a PR in the shared library, a policy since superseded;
  * it gated on VERSION NUMBERS, the one signal measured not to track drift —
    three shared skills carried identical versions with different content;
  * it removed the source with no pointer and no symlink, which for a skill
    silently UNINSTALLS it: `~/.claude/skills` is a symlink to the personal
    skills tree, and that tree is the only one the harness scans.

Graduation is a MOVE
--------------------
Two copies have no owner for the diff; both stay individually valid while the
comparison rots. So skills move and are symlinked back — one implementation,
still visible, drift structurally impossible — and files move with the personal
copy archived behind a pointer. `archive/` is prohibited from execution, which
makes the cutover enforced rather than merely intended.

The pre-flight that matters
---------------------------
A capability can graduate in PIECES, and that is what this exists to prevent.
`findings.py` graduated while the `/findings` skill did not, so the shared layer
shipped a store, two clocks and a statusline segment with no way to work the
list. File-level drift detection is blind to it — there is no pair to compare.

Usage:
    graduate_capability.py skills/who executions/foo.py     # dry run
    graduate_capability.py skills/who --apply
    graduate_capability.py skills/who --apply --force       # override a refusal
    graduate_capability.py --self-check
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

WORKSPACE = Path(os.environ.get("PVRAGON_WORKSPACE", Path.home() / "ai-workspace"))
PERSONAL = WORKSPACE / "my-lib"
SHARED = WORKSPACE / "team-lib"

#: Must never reach the shared layer. Deliberately blunt.
OPERATOR_PATTERNS = [re.compile(p, re.I) for p in
                     (r"your-agent", r"your-username", r"\bthe-operator\b")]

#: A shared file depending on personal-layer CODE is broken for everyone else.
#: `my-lib/runtime/**` is fine — every install has a personal layer to write into.
PERSONAL_CODE = re.compile(
    r"(?:~|\$HOME|/home/[a-z][a-z0-9_-]*)/ai-workspace/my-lib/(?!runtime/)")

TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".json", ".txt", ".toml"}

#: The vocabulary a skill's `category:` must come from (2026-10-16).
VOCABULARY = SHARED / "config" / "skill-categories.yaml"


def _sha(path: Path) -> str:
    if path.is_dir():
        h = hashlib.sha256()
        for f in sorted(path.rglob("*")):
            if f.is_file():
                h.update(f.relative_to(path).as_posix().encode())
                h.update(f.read_bytes())
        return h.hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _texts(path: Path) -> list[tuple[str, str]]:
    files = [path] if path.is_file() else [f for f in path.rglob("*") if f.is_file()]
    out = []
    for f in files:
        if f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            out.append((f.name, f.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return out


def _kind_and_stem(rel: str) -> tuple[str, str]:
    parts = rel.strip("/").split("/")
    if parts[0] == "skills":
        return "skill", parts[1]
    return ("execution" if parts[0] == "executions" else "directive"), Path(parts[-1]).stem


def siblings_left_behind(rel: str) -> list[str]:
    """Other kinds of the SAME capability that would stay in the personal layer.

    The check the rewrite exists for. A stem can appear as an execution, a skill
    and a directive; graduating one and leaving the others is how the shared
    layer ends up shipping something a teammate cannot use.
    """
    kind, stem = _kind_and_stem(rel)
    left: list[str] = []

    if kind != "skill":
        p = PERSONAL / "skills" / stem
        if p.exists() and not p.is_symlink() and not (SHARED / "skills" / stem).exists():
            left.append(f"skill {stem}")

    if kind != "execution":
        for ext in (".py", ".sh"):
            p = PERSONAL / "executions" / f"{stem}{ext}"
            if p.is_file() and not (SHARED / "executions" / p.name).exists():
                left.append(f"execution {p.name}")

    if kind != "directive":
        p = PERSONAL / "directives" / f"{stem}.md"
        if p.is_file() and not (SHARED / "directives" / p.name).exists():
            left.append(f"directive {stem}.md")

    return left


def skill_listing_blocks(skill_md: Path, vocabulary: Path | None = None) -> list[str]:
    """Why a skill may not enter the shared layer on listing grounds ([] when it may).

    A graduated skill is listed for every teammate. Without `listing:` the harness falls back to
    the provenance default and build_registry reports `listing_missing` in team-lib forever; a
    `category:` outside the vocabulary is invisible to find-skill's category filter. Both are
    authorship decisions only the skill's owner can make, so they are refused here, not defaulted.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_registry as BR      # one definition of the allowed values, not two
    fm = BR.read_frontmatter(skill_md) if skill_md.exists() else None
    if not isinstance(fm, dict):
        return [f"{skill_md.name}: no parseable frontmatter — cannot check `listing:` / `category:`"]
    out = []
    if "listing" not in fm:
        out.append(f"{skill_md.name}: no `listing:` — set on | name-only | user-only in the "
                   f"frontmatter before graduating (AGENTS.md metadata standard)")
    elif BR._norm_listing(fm["listing"]) not in BR.LISTING_VALUES:
        out.append(f"{skill_md.name}: `listing: {fm['listing']}` is not one of {list(BR.LISTING_VALUES)}")
    if fm.get("category") is None:
        out.append(f"{skill_md.name}: no `category:` — find-skill cannot filter to it")
    else:
        vocab, err = BR.load_vocabulary(Path("/"), str(vocabulary or VOCABULARY))
        if err:
            out.append(f"{skill_md.name}: {err}")
        elif str(fm["category"]) not in vocab:
            out.append(f"{skill_md.name}: `category: {fm['category']}` is not in "
                       f"{(vocabulary or VOCABULARY).name} — add it there first")
    return out


def check(rel: str) -> dict:
    """Pre-flight one item."""
    src, dst = PERSONAL / rel, SHARED / rel
    r: dict = {"item": rel, "blocks": [], "src": str(src), "dst": str(dst)}

    if src.is_symlink():
        r["blocks"].append("already a symlink — this capability is already graduated")
        r["ok"] = False
        return r
    if not src.exists():
        r["blocks"].append(f"not found in the personal layer: {src}")
        r["ok"] = False
        return r
    if dst.exists() and _sha(src) != _sha(dst):
        r["blocks"].append("exists in the shared layer with DIFFERENT content — reconcile "
                           "first (compared by content hash, not version)")

    for name, text in _texts(src):
        for pat in OPERATOR_PATTERNS:
            if pat.search(text):
                r["blocks"].append(f"{name}: operator identifier /{pat.pattern}/ — generalize first")
                break
        if PERSONAL_CODE.search(text):
            r["blocks"].append(f"{name}: depends on personal-layer CODE — not standalone")

    if rel.startswith("skills/") and src.is_dir():
        r["blocks"].extend(skill_listing_blocks(src / "SKILL.md"))

    left = siblings_left_behind(rel)
    if left:
        r["blocks"].append("SPLIT CAPABILITY — would leave " + ", ".join(left) +
                           " behind; the shared layer would ship a fragment a teammate "
                           "cannot use. Graduate them together.")

    r["ok"] = not r["blocks"]
    return r


def _archive_dir() -> Path:
    d = PERSONAL / "archive" / f"{date.today():%y%m%d}-graduated-to-team-lib"
    d.mkdir(parents=True, exist_ok=True)
    readme = d / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Superseded — graduated to team-lib\n\n"
            "**Do not run anything here.** Per AGENTS.md, code under `archive/` is\n"
            "deprecated and must never be executed. The live implementation is in\n"
            "`team-lib/`.\n\n"
            "Graduation is a move, not a copy: leaving the personal copy in place is\n"
            "exactly what lets the two drift, and the archive prohibition makes the\n"
            "cutover enforced rather than merely intended.\n", encoding="utf-8")
    return d


def graduate(rel: str, apply: bool = False) -> dict:
    src, dst = PERSONAL / rel, SHARED / rel
    kind, _ = _kind_and_stem(rel)
    steps: list[str] = []

    if kind == "skill":
        steps += [f"copy {rel} -> team-lib", "remove the personal directory",
                  "symlink it back (the harness scans only the personal skills tree)"]
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copytree(src, dst)
            shutil.rmtree(src)
            src.symlink_to(dst)
    else:
        arch = _archive_dir()
        steps += [f"copy {rel} -> team-lib", f"archive the personal copy -> {arch.name}/"]
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copy2(src, dst)
                if src.suffix == ".sh" or os.access(src, os.X_OK):
                    dst.chmod(dst.stat().st_mode | 0o111)
            moved = subprocess.run(
                ["git", "-C", str(PERSONAL), "mv", rel,
                 str((arch / src.name).relative_to(PERSONAL))],
                capture_output=True, text=True)
            if moved.returncode != 0 and src.exists():
                shutil.move(str(src), str(arch / src.name))

    steps.append("UPDATE BOTH REGISTRIES — move the entry, leaving a pointer comment "
                 "behind. Not automated: they are hand-curated YAML with prose.")
    return {"item": rel, "kind": kind, "steps": steps, "applied": apply}


def run(items: list[str], apply: bool = False, force: bool = False) -> dict:
    """Graduate one or more capabilities from the personal to the shared layer.

    Args:
        items: workspace-relative paths, e.g. "skills/who", "executions/foo.py".
        apply: perform the move (default: dry run).
        force: proceed despite pre-flight blocks.

    Returns:
        dict with keys: status ("ok" | "blocked" | "error"), checked, blocked, graduated.
    """
    if not PERSONAL.is_dir() or not SHARED.is_dir():
        return {"status": "error", "error": f"layers not found under {WORKSPACE}"}

    checked = [check(i) for i in items]
    blocked = [c for c in checked if not c["ok"]]
    if blocked and not force:
        return {"status": "blocked", "checked": checked, "blocked": blocked, "graduated": []}

    return {"status": "ok", "checked": checked, "blocked": blocked,
            "graduated": [graduate(c["item"], apply=apply) for c in checked]}


def self_check() -> int:
    """Two-sided, on synthetic SKILL.md files: a complete skill passes; each gap MUST be refused."""
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        vocab = d / "vocab.yaml"
        vocab.write_text("categories:\n  workspace: W.\n")
        cases = {   # name: (frontmatter body, must_pass)
            "good": ("listing: name-only\ncategory: workspace\n", True),
            "bare-on": ("listing: on\ncategory: workspace\n", True),     # YAML True -> "on"
            "no-listing": ("category: workspace\n", False),
            "bad-listing": ("listing: loud\ncategory: workspace\n", False),
            "off": ("listing: off\ncategory: workspace\n", False),      # sidecar-only value
            "no-category": ("listing: name-only\n", False),
            "bad-category": ("listing: name-only\ncategory: acme-billing\n", False),
        }
        for name, (body, must_pass) in cases.items():
            sk = d / name / "SKILL.md"
            sk.parent.mkdir()
            sk.write_text(f"---\nname: {name}\nsummary: S.\n{body}---\nbody\n")
            blocks = skill_listing_blocks(sk, vocab)
            if bool(blocks) == must_pass:
                print(f"FAIL: {name}: {'refused' if blocks else 'passed'} — {blocks}")
                ok = False
        if not skill_listing_blocks(d / "missing" / "SKILL.md", vocab):
            print("FAIL: a skill with no SKILL.md passed the listing check"); ok = False
    print("self-check: PASS" if ok else "self-check: FAIL")
    return 0 if ok else 1


def main() -> int:
    if "--self-check" in sys.argv[1:]:
        return self_check()
    ap = argparse.ArgumentParser(
        description="Graduate a capability from my-lib to team-lib (a MOVE, not a copy).")
    ap.add_argument("items", nargs="+", help="e.g. skills/who executions/foo.py")
    ap.add_argument("--apply", action="store_true", help="perform the move (default: dry run)")
    ap.add_argument("--force", action="store_true", help="proceed despite pre-flight blocks")
    args = ap.parse_args()

    r = run(args.items, apply=args.apply, force=args.force)
    if r["status"] == "error":
        print(f"Error: {r['error']}", file=sys.stderr)
        return 2

    for c in r["checked"]:
        print(f"[{'OK' if c['ok'] else 'REFUSED'}] {c['item']}")
        for b in c["blocks"]:
            print(f"    x {b}")

    if r["status"] == "blocked":
        print("\nNothing moved. Fix the above, or re-run with --force if the split is\n"
              "intended and you will record why.", file=sys.stderr)
        return 1

    print(f"\n-- {'APPLIED' if args.apply else 'dry run'} --")
    for g in r["graduated"]:
        print(f"  {g['item']} ({g['kind']})")
        for s in g["steps"]:
            print(f"    - {s}")
    if not args.apply:
        print("\nRe-run with --apply to perform it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
