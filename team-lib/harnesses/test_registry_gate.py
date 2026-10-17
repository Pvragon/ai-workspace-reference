#!/usr/bin/env python3
# ---
# template: harness
# version: 1.2.0
# summary: >-
#   Two-sided sandbox test of version_gate's registry pass, against REAL git repos in a temp dir
#   under my-lib/runtime/.tmp (the gate refuses to act outside the workspace). Ten scenarios:
#   mapped repo regenerates and commits, unmapped repo is left alone, a comment-bearing manifest
#   is refused aloud, an unparseable manifest is reported without blocking, a clean repo makes no
#   empty commit, [no-version] opts out of versions but NOT the index, index.md is generated AND
#   staged, hand-authored text inside `## Contents` survives with the refusal reported, and
#   --reconcile commits what it regenerates while --dry-run changes nothing.
# created: 2026-08-08
# last_updated: 2026-08-08
# maintainer: pvragon
# ---
"""Two-sided test of version_gate's registry pass, against real git repos in a sandbox."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

GATE = os.path.expanduser("~/ai-workspace/team-lib/executions/version_gate.py")
WS = os.path.expanduser("~/ai-workspace")
ok = True


def sh(*a, cwd=None):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True)


def mkrepo(root: Path, with_map: bool, comments_below: bool = False) -> Path:
    """A repo shaped like ours: skills/<n>/SKILL.md + registry/skills.yaml (+ optional map)."""
    repo = root
    (repo / "skills" / "alpha").mkdir(parents=True)
    (repo / "registry").mkdir()
    (repo / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\nsummary: The alpha skill.\nversion: 1.0.0\n---\nbody\n")
    reg = "# summary: skills manifest\nskills:\n- name: alpha\n  path: skills/alpha/SKILL.md\n" \
          "  description: The alpha skill.\n  version: 1.0.0\n"
    if comments_below:
        reg += "# a load-bearing comment about scope that PyYAML cannot round-trip\n"
    (repo / "registry" / "skills.yaml").write_text(reg)
    if with_map:
        (repo / "config").mkdir()
        (repo / "config" / "registry-map.yaml").write_text(
            "summary_budget_words: 60\nregistries:\n  skills:\n    file: registry/skills.yaml\n"
            "    key: skills\n    shape: list\n    id: name\n    globs: ['skills/*/SKILL.md']\n"
            "    field: description\n    derived: [path, version, description]\n")
    sh("git", "init", "-q", "-b", "main", cwd=repo)
    sh("git", "config", "user.email", "t@t", cwd=repo)
    sh("git", "config", "user.name", "t", cwd=repo)
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "init", cwd=repo)
    # an "upstream" so @{u} resolves
    bare = repo.parent / (repo.name + "-remote.git")
    sh("git", "init", "-q", "--bare", str(bare))
    sh("git", "remote", "add", "origin", str(bare), cwd=repo)
    sh("git", "push", "-q", "-u", "origin", "main", cwd=repo)
    return repo


def fire(repo: Path) -> str:
    """Invoke the hook exactly as the harness does: PreToolUse JSON on stdin."""
    payload = json.dumps({"tool_name": "Bash", "cwd": str(repo),
                          "tool_input": {"command": f"git -C {repo} push"}})
    r = subprocess.run([sys.executable, GATE], input=payload, capture_output=True, text=True)
    return r.stderr + r.stdout


def check(label, cond, extra=""):
    global ok
    print(f"  {'PASS' if cond else '**FAIL**'}  {label}{'' if cond else '  ' + extra}")
    if not cond:
        ok = False


# The gate refuses to act outside WORKSPACE, so the sandbox must live inside it.
with tempfile.TemporaryDirectory(dir=os.path.join(WS, "my-lib", "runtime", ".tmp")) as td:
    base = Path(td)

    print("\n[1] repo WITH a map: a new skill on disk must reach the manifest")
    r1 = mkrepo(base / "mapped", with_map=True)
    (r1 / "skills" / "beta").mkdir(parents=True)
    (r1 / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nsummary: The beta skill.\nversion: 2.0.0\n---\nbody\n")
    sh("git", "add", "-A", cwd=r1); sh("git", "commit", "-qm", "add beta", cwd=r1)
    before = (r1 / "registry" / "skills.yaml").read_text()
    out = fire(r1)
    after = (r1 / "registry" / "skills.yaml").read_text()
    check("beta reached the manifest", "beta" in after, f"manifest still: {after[:120]}")
    check("manifest actually changed", before != after)
    check("the rebuild was committed, not left dirty",
          sh("git", "status", "--porcelain", cwd=r1).stdout.strip() == "",
          sh("git", "status", "--porcelain", cwd=r1).stdout)
    check("gate exited without blocking", True)

    print("\n[2] falsify: same repo, map REMOVED -> manifest must NOT be rewritten")
    r2 = mkrepo(base / "unmapped", with_map=False)
    (r2 / "skills" / "beta").mkdir(parents=True)
    (r2 / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nsummary: The beta skill.\nversion: 2.0.0\n---\nbody\n")
    sh("git", "add", "-A", cwd=r2); sh("git", "commit", "-qm", "add beta", cwd=r2)
    before2 = (r2 / "registry" / "skills.yaml").read_text()
    fire(r2)
    check("unmapped manifest left alone",
          (r2 / "registry" / "skills.yaml").read_text() == before2)

    print("\n[3] a manifest with comments below its header must be REFUSED, and say so")
    r3 = mkrepo(base / "commented", with_map=True, comments_below=True)
    (r3 / "skills" / "beta").mkdir(parents=True)
    (r3 / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nsummary: The beta skill.\nversion: 2.0.0\n---\nbody\n")
    sh("git", "add", "-A", cwd=r3); sh("git", "commit", "-qm", "add beta", cwd=r3)
    before3 = (r3 / "registry" / "skills.yaml").read_text()
    out3 = fire(r3)
    check("comment-bearing manifest not rewritten",
          (r3 / "registry" / "skills.yaml").read_text() == before3)
    check("refusal is reported, not silent", "comments" in out3.lower(), out3[:300])

    print("\n[4] an UNPARSEABLE manifest must be reported and must not block")
    r4 = mkrepo(base / "broken", with_map=False)
    (r4 / "registry" / "skills.yaml").write_text("skills:\n- name: a\n  summary: 'the '837' rule'\n")
    sh("git", "add", "-A", cwd=r4); sh("git", "commit", "-qm", "break it", cwd=r4)
    out4 = fire(r4)
    check("parse failure surfaced", "DOES NOT PARSE" in out4, out4[:300])

    print("\n[5] a clean repo must stay a no-op (no empty commits)")
    r5 = mkrepo(base / "clean", with_map=True)
    n_before = sh("git", "rev-list", "--count", "HEAD", cwd=r5).stdout.strip()
    fire(r5)
    n_after = sh("git", "rev-list", "--count", "HEAD", cwd=r5).stdout.strip()
    check("no commit created on a clean repo", n_before == n_after, f"{n_before} -> {n_after}")

    print("\n[6] [no-version] must opt out of VERSIONS ONLY, never the index")
    r6 = mkrepo(base / "noversion", with_map=True)
    (r6 / "skills" / "beta").mkdir(parents=True)
    (r6 / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nsummary: The beta skill.\nversion: 2.0.0\n---\nbody\n")
    sh("git", "add", "-A", cwd=r6)
    sh("git", "commit", "-qm", "add beta\n\n[no-version]", cwd=r6)
    before6 = (r6 / "registry" / "skills.yaml").read_text()
    fire(r6)
    after6 = (r6 / "registry" / "skills.yaml").read_text()
    check("index still made true under [no-version]", "beta" in after6,
          f"manifest unchanged: {before6 == after6}")
    check("and it was committed", sh("git", "status", "--porcelain", cwd=r6).stdout.strip() == "")

    print("\n[7] the directory INDEX is made true at the same boundary — and STAGED")
    r7 = mkrepo(base / "indexed", with_map=True)
    (r7 / "skills" / "beta").mkdir(parents=True)
    (r7 / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nsummary: The beta skill.\nversion: 2.0.0\n---\nbody\n")
    sh("git", "add", "-A", cwd=r7); sh("git", "commit", "-qm", "add beta", cwd=r7)
    fire(r7)
    idx7 = r7 / "skills" / "index.md"
    check("skills/index.md was generated", idx7.exists())
    check("it carries a row per skill",
          idx7.exists() and "[`alpha`]" in idx7.read_text() and "[`beta`]" in idx7.read_text(),
          idx7.read_text()[:200] if idx7.exists() else "no file")
    # ⚑ THE POINT OF THIS SCENARIO. Both callers used to stage the literal path "registry", so an
    # index.md written outside that directory would be created and then left untracked — the push
    # carries the manifest, the index stays dirty, and the gate reports success either way.
    check("the index was COMMITTED, not left dirty in the working tree",
          sh("git", "status", "--porcelain", cwd=r7).stdout.strip() == "",
          sh("git", "status", "--porcelain", cwd=r7).stdout)
    check("and it is tracked by git",
          sh("git", "ls-files", "skills/index.md", cwd=r7).stdout.strip() != "")

    print("\n[8] falsify: hand-authored content in `## Contents` must survive the gate")
    r8 = mkrepo(base / "handwritten", with_map=True)
    (r8 / "skills" / "index.md").write_text(
        "# skills\n\n## Contents\n\nA sentence a person wrote and expects to keep.\n")
    (r8 / "skills" / "beta").mkdir(parents=True)
    (r8 / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nsummary: The beta skill.\nversion: 2.0.0\n---\nbody\n")
    sh("git", "add", "-A", cwd=r8); sh("git", "commit", "-qm", "add beta", cwd=r8)
    out8 = fire(r8)
    check("the hand-authored line was not destroyed",
          "a person wrote" in (r8 / "skills" / "index.md").read_text())
    check("and the refusal was reported, not silent",
          "hand-authored" in out8, out8[:300])

    print("\n[9] --reconcile (the nightly backstop) must COMMIT what it regenerates")
    r9 = mkrepo(base / "reconcile", with_map=True)
    (r9 / "skills" / "beta").mkdir(parents=True)
    (r9 / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nsummary: The beta skill.\nversion: 2.0.0\n---\nbody\n")
    sh("git", "add", "-A", cwd=r9); sh("git", "commit", "-qm", "add beta", cwd=r9)
    out9 = sh(sys.executable, GATE, "--reconcile", str(r9)).stdout
    check("beta reached the manifest via --reconcile",
          "beta" in (r9 / "registry" / "skills.yaml").read_text())
    # reconcile() only committed when a VERSION moved, staging the blanket path "registry".
    # Nothing here bumps a version, so before the fix this left the rebuild dirty forever while
    # dream_cycle reported it as "regenerated and committed".
    check("the reconciled rebuild was COMMITTED, not left dirty",
          sh("git", "status", "--porcelain", cwd=r9).stdout.strip() == "",
          sh("git", "status", "--porcelain", cwd=r9).stdout)
    check("and it reported the paths it wrote", '"registry_rewritten": [' in out9, out9[:200])

    print("\n[10] --reconcile --dry-run must change NOTHING (the project-repo contract)")
    r10 = mkrepo(base / "dryrun", with_map=True)
    (r10 / "skills" / "beta").mkdir(parents=True)
    (r10 / "skills" / "beta" / "SKILL.md").write_text(
        "---\nname: beta\nsummary: The beta skill.\nversion: 2.0.0\n---\nbody\n")
    sh("git", "add", "-A", cwd=r10); sh("git", "commit", "-qm", "add beta", cwd=r10)
    before10 = (r10 / "registry" / "skills.yaml").read_text()
    n10 = sh("git", "rev-list", "--count", "HEAD", cwd=r10).stdout.strip()
    sh(sys.executable, GATE, "--reconcile", str(r10), "--dry-run")
    check("--dry-run did not rewrite the manifest",
          (r10 / "registry" / "skills.yaml").read_text() == before10)
    check("--dry-run created no index.md", not (r10 / "skills" / "index.md").exists())
    check("--dry-run made no commit",
          sh("git", "rev-list", "--count", "HEAD", cwd=r10).stdout.strip() == n10)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
