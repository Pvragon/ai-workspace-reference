#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.3
# summary: "Exposes shared skills to the harness: links ~/.claude/skills to the personal layer
#   (a symlink, or per-entry links in a real directory) and points my-lib/skills at every
#   unshadowed team-lib skill and external skill (ext-<name>). Reports a stale skill listing map.
#   Idempotent; never deletes anything it did not create."
# created: 2026-08-01
# last_updated: 2026-10-21
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
#
# ⚑ ~/.claude/skills MAY BE A REAL DIRECTORY (2026-10-16). Since the 2026-10-12 Omarchy restore it
# is a directory of per-skill links, because it also holds entries that live nowhere in the
# workspace (Omarchy's own `omarchy` and `diagnose-crash`, and the harness-managed `synced/` tree).
# This script used to refuse that layout outright, so every skill added since was invisible
# outside my-lib sessions (`triage-clickup-inbox` was the first). It now keeps such a directory in
# step entry by entry: creates a missing link to my-lib/skills/<name>, leaves a correct one alone,
# and REPORTS — never deletes or repoints — anything it does not own.
#
# POINTER NAMES ARE THE skillOverrides KEYS (2026-10-16). What the harness shows the model for a
# skill is set by Claude Code's `skillOverrides`, keyed by the name the harness lists — the entry
# name here (`ext-pdf`), not the skill's frontmatter `name:` (`pdf` would hit the synced
# `anthropic-skills:pdf` instead). So renaming a pointer orphans its listing; build_skill_overrides
# reports the orphan. One pointer per skill: the hand-made duplicate `ext-humanizer` (a second name
# for `ext-blader-humanizer`) was retired for exactly this reason.

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
            # Skip a pack's own nested node_modules / vendored copies, and adapter trees written
            # for ANOTHER agent (rezvani's .gemini/ holds 87 Gemini-only command conversions).
            if any(p in {"node_modules", ".git", ".gemini"} for p in skill_dir.parts):
                continue
            candidates.setdefault(f"ext-{skill_dir.name}", []).append(skill_dir)

        for name, dirs in sorted(candidates.items()):
            rel = lambda d: d.relative_to(ext_root).parts  # noqa: E731
            # A copy outside hidden folders (.agents/, .gemini/, .claude/) always wins; then the
            # shallowest. Depth used to rank first, so rezvani's `.gemini/skills/<name>` beat its
            # deeper canonical `<team>/<name>/skills/<name>` (2026-10-21 re-pin). Never a hard
            # exclusion: arpeeketi's only copy lives under .claude/skills/.
            ranked = sorted(dirs, key=lambda d: (sum(p.startswith(".") for p in rel(d)),
                                                 len(rel(d)),
                                                 str(d)))
            best = ranked[0]
            if name in found:
                if found[name] != best:
                    conflicts.append((name, found[name], best))
                continue
            found[name] = best

    return found, conflicts


def sync_harness_entries(apply, report):
    """Per-entry links from a REAL ~/.claude/skills into my-lib/skills.

    Ours = a link whose target resolves to the same place as my-lib/skills/<name>. Everything
    else in the directory is foreign: reported, never touched. A link we would create is named
    after the my-lib entry and points at my-lib/skills/<name> (not at its resolved target), so
    shadowing and graduation keep working through the personal layer exactly as with the
    single-symlink layout.
    """
    personal = {e.name: e for e in sorted(PERSONAL_SKILLS.iterdir())
                if e.name not in SKIP_NAMES and e.name != "synced" and (e / "SKILL.md").is_file()}
    for name, src in personal.items():
        dst = HARNESS_SKILLS / name
        if dst.is_symlink() or dst.exists():
            if os.path.realpath(dst) == os.path.realpath(src):
                report("harness_ok", f"harness/{name}")
            else:
                report("warn", f"harness/{name} is not a link to {src} — foreign, left alone")
            continue
        if apply:
            dst.symlink_to(src, target_is_directory=True)
        report("harness", f"~/.claude/skills/{name} -> {src}")
    # Foreign entries the harness sees that the personal layer does not provide (e.g. Omarchy's).
    # Information only: they are legitimate, just not ours to manage.
    for e in sorted(HARNESS_SKILLS.iterdir()):
        if e.name in personal or e.name in SKIP_NAMES or e.name == "synced":
            continue
        if e.is_symlink() and not e.exists():
            report("warn", f"harness/{e.name} is a DANGLING link ({os.readlink(e)}) — left alone")
        elif (e / "SKILL.md").is_file():
            report("foreign", f"harness/{e.name} -> {os.path.realpath(e)} (not from my-lib; kept)")


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
            report("ok", f"{HARNESS_SKILLS} is a real directory — syncing per-entry links")
            if PERSONAL_SKILLS.is_dir():
                sync_harness_entries(apply, report)
            return True
        if apply:
            HARNESS_SKILLS.rmdir()
    if apply:
        HARNESS_SKILLS.parent.mkdir(parents=True, exist_ok=True)
        HARNESS_SKILLS.symlink_to(PERSONAL_SKILLS, target_is_directory=True)
    report("write", f"~/.claude/skills -> {PERSONAL_SKILLS}")
    return True


def listing_status_line():
    """One line, or None: is the skill listing map behind the skills the harness now sees?
    Never raises — a listing problem must not cost anyone their skill links."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build_skill_overrides as BSO
        r = BSO.run("installed", WORKSPACE / "my-lib", HARNESS_SKILLS)
    except Exception as exc:                     # noqa: BLE001  report, never block linking
        return f"skill listing: not checked ({exc.__class__.__name__})"
    if r.get("status") != "ok":
        return f"skill listing: not checked — {r.get('error')}"
    # Worded as what the agent does, never a command for the owner to type (standing rule; same
    # wording as build_skill_overrides --check). Regenerating writes my-lib/config only; installing
    # writes the protected settings.json, so it takes the owner's one-time approval.
    if r["stale"]:
        return ("skill listing map STALE — the agent regenerates it with build_skill_overrides.py, "
                "then installs it with install_skill_overrides.py --apply (one settings.json approval)")
    d = r["installed"]
    if d["missing"] or d["stale"]:
        return (f"skill listing not installed ({len(d['missing'])} key(s) differ) — the agent runs "
                f"install_skill_overrides.py --apply (one settings.json approval)")
    return None


def main():
    ap = argparse.ArgumentParser(description="Expose shared skills to the agent harness.")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    ap.add_argument("--quiet", action="store_true", help="summary line only")
    ap.add_argument("--self-check", action="store_true", help="run the two-sided self-check")
    args = ap.parse_args()
    if args.self_check:
        return self_check()
    apply = not args.dry_run

    counts = {"ok": 0, "write": 0, "warn": 0, "shadowed": 0, "repaired": 0, "harness": 0,
              "harness_ok": 0, "foreign": 0}
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
            if kind in ("write", "warn", "repaired", "shadowed", "harness", "foreign"):
                prefix = {"write": "  +", "warn": "  !", "repaired": "  ~", "shadowed": "  =",
                          "harness": "  +", "foreign": "  ·"}[kind]
                print(f"{prefix} {msg}")

    verb = "would link" if args.dry_run else "linked"
    print(f"link_skills: {len(shared)} shared skill(s); {counts['write']} {verb}, "
          f"{counts['ok']} already correct, {counts['repaired']} repaired, "
          f"{counts['shadowed']} shadowed by personal, {counts['warn']} warning(s)")
    if counts["harness"] or counts["foreign"]:
        print(f"link_skills: harness directory — {counts['harness']} per-entry link(s) "
              f"{'to add' if args.dry_run else 'added'}, {counts['harness_ok']} already linked, "
              f"{counts['foreign']} foreign entr(ies) kept")
    line = listing_status_line()
    if line:
        print(f"link_skills: {line}")
    if not harness_ok:
        print("link_skills: harness cannot see the personal layer — see the warning above")
        return 1
    return 0


def self_check():
    """Two-sided, in a temp tree: a real harness directory gains missing links, keeps correct
    and foreign ones byte-for-byte, and never loses an entry."""
    import tempfile
    global PERSONAL_SKILLS, HARNESS_SKILLS
    saved = (PERSONAL_SKILLS, HARNESS_SKILLS)
    ok = True
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            PERSONAL_SKILLS = root / "my-lib" / "skills"
            HARNESS_SKILLS = root / "home" / ".claude" / "skills"
            for n in ("linked", "missing"):
                (PERSONAL_SKILLS / n).mkdir(parents=True)
                (PERSONAL_SKILLS / n / "SKILL.md").write_text("---\nname: x\n---\n")
            (PERSONAL_SKILLS / "_archived").mkdir()
            sysd = root / "usr" / "omarchy"
            sysd.mkdir(parents=True)
            (sysd / "SKILL.md").write_text("---\nname: omarchy\n---\n")
            HARNESS_SKILLS.mkdir(parents=True)
            (HARNESS_SKILLS / "linked").symlink_to(PERSONAL_SKILLS / "linked")
            (HARNESS_SKILLS / "omarchy").symlink_to(sysd)
            (HARNESS_SKILLS / "dead").symlink_to(root / "nowhere")
            (HARNESS_SKILLS / "synced").mkdir()
            before = {e.name: os.readlink(e) if e.is_symlink() else "dir"
                      for e in HARNESS_SKILLS.iterdir()}
            seen = []
            if not ensure_harness_link(False, lambda k, m: seen.append((k, m))):
                print("FAIL: a real harness directory was refused"); ok = False
            if (HARNESS_SKILLS / "missing").exists():
                print("FAIL: dry-run created a link"); ok = False
            seen.clear()
            ensure_harness_link(True, lambda k, m: seen.append((k, m)))
            kinds = [k for k, _ in seen]
            if os.path.realpath(HARNESS_SKILLS / "missing") != str((PERSONAL_SKILLS / "missing").resolve()):
                print("FAIL: a missing per-entry link was not created"); ok = False
            for name, tgt in before.items():
                now = HARNESS_SKILLS / name
                if not (now.is_symlink() or now.exists()):
                    print(f"FAIL: harness entry {name} was DELETED"); ok = False
                elif tgt != "dir" and os.readlink(now) != tgt:
                    print(f"FAIL: harness entry {name} was repointed"); ok = False
            if "foreign" not in kinds or not any("DANGLING" in m for _, m in seen):
                print(f"FAIL: foreign / dangling entries were not reported: {seen}"); ok = False
            if (HARNESS_SKILLS / "_archived").exists():
                print("FAIL: a bookkeeping directory was linked as a skill"); ok = False
            seen.clear()
            ensure_harness_link(True, lambda k, m: seen.append((k, m)))
            if any(k == "harness" for k, _ in seen):
                print("FAIL: a second run was not a no-op"); ok = False
    finally:
        PERSONAL_SKILLS, HARNESS_SKILLS = saved
    print("self-check: PASS" if ok else "self-check: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
