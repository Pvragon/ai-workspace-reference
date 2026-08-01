#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Exposes the shared skill library to the agent harness: wires ~/.claude/skills to the
#   personal layer and creates a pointer in my-lib/skills for every team-lib skill (and every
#   external-pack skill as ext-<name>) that the personal layer does not already shadow.
#   Idempotent. Without it a fresh install has a 97-skill library it cannot invoke."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# Why this script exists
# ----------------------
# The harness discovers skills in ~/.claude/skills. In this workspace that path is a symlink
# to my-lib/skills — the personal layer — and shared skills reach the agent as symlinks placed
# inside it. That is deliberate: it is what makes a local skill shadow a shared one of the same
# name (Operating Principle #1's search hierarchy), and it is why graduation is a MOVE.
#
# Nothing created either link. They had accumulated by hand on the machine that invented the
# convention, so every check passed there and the gap was invisible. The pristine-container run
# on 2026-08-01 measured what a new teammate actually gets: ~/.claude/skills absent, my-lib/skills
# empty, 97 shared skills installed and none of them invocable.
#
# Precedence, deliberately:
#   1. a real directory already in my-lib/skills  -> personal skill wins, never touched
#   2. team-lib/skills/<name>                     -> pointer <name>
#   3. team-lib/skills/_external/<pack>/**/SKILL.md -> pointer ext-<skill-dir-name>
# Internal beats external on a name collision, and the first pack wins between externals; both
# cases are reported rather than silently resolved.

import argparse
import os
import sys
from pathlib import Path

WORKSPACE = Path(os.environ.get("PVRAGON_WORKSPACE", Path.home() / "ai-workspace"))
TEAM_SKILLS = WORKSPACE / "team-lib" / "skills"
PERSONAL_SKILLS = WORKSPACE / "my-lib" / "skills"
HARNESS_SKILLS = Path.home() / ".claude" / "skills"

# Not skills: bookkeeping directories and the folder README.
SKIP_NAMES = {"_external", "_archived", "_archive", "index.md", "README.md"}


def discover_shared():
    """Return {pointer_name: target_path} for every shared skill, internal first.

    A skill is a directory containing SKILL.md. External packs nest theirs at varying
    depths, so they are found by walking for SKILL.md rather than by assuming a layout.
    """
    found, conflicts = {}, []

    if TEAM_SKILLS.is_dir():
        for entry in sorted(TEAM_SKILLS.iterdir()):
            if entry.name in SKIP_NAMES or not entry.is_dir():
                continue
            if (entry / "SKILL.md").is_file():
                found[entry.name] = entry

    ext_root = TEAM_SKILLS / "_external"
    if ext_root.is_dir():
        # Packs publish the same skill at more than one path — paramchoudhary ships every
        # one under both skills/ and .agents/skills/. Gather all candidates first and
        # choose deliberately, because "whichever the walk hit first" picked the hidden
        # mirror on 14 of them.
        candidates = {}
        for skill_md in sorted(ext_root.rglob("SKILL.md")):
            skill_dir = skill_md.parent
            # Skip a pack's own nested node_modules / vendored copies.
            if any(p in {"node_modules", ".git"} for p in skill_dir.parts):
                continue
            candidates.setdefault(f"ext-{skill_dir.name}", []).append(skill_dir)

        for name, dirs in sorted(candidates.items()):
            rel = lambda d: d.relative_to(ext_root).parts  # noqa: E731
            # Shallowest path wins; a hidden component (.agents/, .claude/) loses a tie.
            # Never a hard exclusion: arpeeketi's only copy lives under .claude/skills/.
            ranked = sorted(dirs, key=lambda d: (len(rel(d)),
                                                 sum(p.startswith(".") for p in rel(d)),
                                                 str(d)))
            best = ranked[0]
            if name in found:
                if found[name] != best:
                    conflicts.append((name, found[name], best))
                continue
            found[name] = best

    return found, conflicts


def ensure_harness_link(apply, report):
    """~/.claude/skills -> my-lib/skills, without ever clobbering real content."""
    if HARNESS_SKILLS.is_symlink():
        target = Path(os.path.realpath(HARNESS_SKILLS))
        if target == PERSONAL_SKILLS.resolve():
            report("ok", f"~/.claude/skills -> {PERSONAL_SKILLS}")
        else:
            report("warn", f"~/.claude/skills points elsewhere ({target}) — left alone")
        return True
    if HARNESS_SKILLS.exists():
        if any(HARNESS_SKILLS.iterdir()):
            report("warn", f"{HARNESS_SKILLS} is a real non-empty directory — left alone; "
                           f"shared skills will not be visible until it is a symlink to {PERSONAL_SKILLS}")
            return False
        if apply:
            HARNESS_SKILLS.rmdir()
    if apply:
        HARNESS_SKILLS.parent.mkdir(parents=True, exist_ok=True)
        HARNESS_SKILLS.symlink_to(PERSONAL_SKILLS, target_is_directory=True)
    report("write", f"~/.claude/skills -> {PERSONAL_SKILLS}")
    return True


def main():
    ap = argparse.ArgumentParser(description="Expose shared skills to the agent harness.")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    ap.add_argument("--quiet", action="store_true", help="summary line only")
    args = ap.parse_args()
    apply = not args.dry_run

    counts = {"ok": 0, "write": 0, "warn": 0, "shadowed": 0, "repaired": 0}
    lines = []

    def report(kind, msg):
        counts[kind] = counts.get(kind, 0) + 1
        lines.append((kind, msg))

    if not TEAM_SKILLS.is_dir():
        print(f"link_skills: no shared skills at {TEAM_SKILLS} — nothing to do")
        return 0
    if apply:
        PERSONAL_SKILLS.mkdir(parents=True, exist_ok=True)

    shared, conflicts = discover_shared()
    for name, target in sorted(shared.items()):
        link = PERSONAL_SKILLS / name
        if link.is_symlink():
            current = Path(os.path.realpath(link))
            if current == target.resolve():
                report("ok", f"{name}")
            elif not link.exists():
                # Dangling: the shared layer moved. Repointing is safe; the personal
                # layer never owned this entry, it only ever pointed at the shared one.
                if apply:
                    link.unlink()
                    link.symlink_to(target, target_is_directory=True)
                report("repaired", f"{name} (was dangling)")
            else:
                report("warn", f"{name} points at {current}, not {target} — left alone")
        elif link.exists():
            # A real directory here is a personal skill. It wins, by design.
            report("shadowed", f"{name} (personal skill shadows the shared one)")
        else:
            if apply:
                link.symlink_to(target, target_is_directory=True)
            report("write", f"{name} -> {target}")

    harness_ok = ensure_harness_link(apply, report)

    for name, kept, dropped in conflicts:
        report("warn", f"name collision on {name}: kept {kept}, ignored {dropped}")

    if not args.quiet:
        for kind, msg in lines:
            if kind in ("write", "warn", "repaired", "shadowed"):
                prefix = {"write": "  +", "warn": "  !", "repaired": "  ~", "shadowed": "  ="}[kind]
                print(f"{prefix} {msg}")

    verb = "would link" if args.dry_run else "linked"
    print(f"link_skills: {len(shared)} shared skill(s); {counts['write']} {verb}, "
          f"{counts['ok']} already correct, {counts['repaired']} repaired, "
          f"{counts['shadowed']} shadowed by personal, {counts['warn']} warning(s)")
    if not harness_ok:
        print("link_skills: harness cannot see the personal layer — see the warning above")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
