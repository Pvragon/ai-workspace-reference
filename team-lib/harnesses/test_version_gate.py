#!/usr/bin/env python3
# ---
# template: harness
# version: 1.0.1
# summary: "Paired-case harness for version_gate.py's repo resolution and its refusal to version a
#   generated artifact. Builds throwaway git repos under a scratch VERSION_GATE_ROOT and drives the
#   hook exactly as the harness does — via a stdin JSON payload — so the assertions cover the real
#   entry point rather than an imported helper. Each case states what MUST happen and what MUST NOT."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
"""test_version_gate.py — prove the gate versions the repo being PUSHED.

Why this exists
---------------
The gate reads command TEXT, not an expanded shell, so it has to infer which repo a
push targets. It got this wrong twice in the same way:

  `git -C $VAR push`        -> literal "$VAR", resolved to nothing   (fixed 2026-07-31)
  `cd <repo> && git push`   -> the `cd` is invisible, session cwd wins (fixed 2026-08-01)

The second one was not theoretical. Pushing team-lib immediately after committing in
the public repo made the gate evaluate the PUBLIC repo: it bumped versions inside a
generated artifact, while team-lib — the actual source — shipped unversioned. Both
halves of that failure get a case here, plus the silent-success shape that hid it
(the gate logged a bump and the source tree never changed).

    python3 harnesses/test_version_gate.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "executions" / "version_gate.py"

VERSIONED_MD = """---
template: skill-definition
version: 1.2.0
last_updated: 2026-01-01
---

# A skill
Body text.
"""


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def git(repo, *args):
    return run("git", "-C", str(repo), *args)


def make_repo(path: Path, body: str) -> None:
    """A repo with an upstream and one unpushed commit that changes a versioned file."""
    origin = path.parent / (path.name + ".origin")
    run("git", "init", "-q", "--bare", str(origin))
    run("git", "init", "-q", "-b", "main", str(path))
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    (path / "skills").mkdir(parents=True, exist_ok=True)
    (path / "registry").mkdir(parents=True, exist_ok=True)
    f = path / "skills" / "thing.md"
    f.write_text(VERSIONED_MD, encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "initial")
    git(path, "remote", "add", "origin", str(origin))
    git(path, "push", "-q", "-u", "origin", "main")
    # the unpushed change: body differs, version deliberately left alone
    f.write_text(VERSIONED_MD.replace("Body text.", body), encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "change the body, leave the version")


def fire(cmd: str, cwd: Path, root: Path):
    payload = json.dumps({"tool_name": "Bash", "cwd": str(cwd),
                          "tool_input": {"command": cmd}})
    env = dict(os.environ, VERSION_GATE_ROOT=str(root), HOME=str(root / "fakehome"))
    (root / "fakehome").mkdir(exist_ok=True)
    return subprocess.run([sys.executable, str(GATE)], input=payload,
                          capture_output=True, text=True, env=env)


def version_of(path: Path) -> str:
    m = re.search(r"^version:\s*([\d.]+)", path.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "?"


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="vgate-"))
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
        if not cond:
            fails.append(name)

    try:
        team = root / "team-lib"
        public = root / "projects" / "ai-workspace-reference"
        public.parent.mkdir(parents=True, exist_ok=True)
        make_repo(team, "team body")
        make_repo(public, "public body")

        print("case 1: `cd <repo> && git push` versions THAT repo, not the session cwd")
        # The exact shape that failed: session cwd is the public repo, the push targets team-lib.
        fire(f"cd {team} && git push", cwd=public, root=root)
        check("team-lib bumped 1.2.0 -> 1.2.1", version_of(team / "skills/thing.md") == "1.2.1",
              f"got {version_of(team / 'skills/thing.md')}")
        check("public left alone (the cwd was NOT versioned)",
              version_of(public / "skills/thing.md") == "1.2.0",
              f"got {version_of(public / 'skills/thing.md')}")
        check("bump was COMMITTED, not left dirty",
              "chore(version)" in git(team, "log", "--format=%s", "-1").stdout)

        print("case 2: pushing the generated public repo is refused outright")
        before = version_of(public / "skills/thing.md")
        r = fire(f"cd {public} && git push", cwd=public, root=root)
        check("public still unversioned by the gate",
              version_of(public / "skills/thing.md") == before, f"got {before}")
        check("says why", "generated public repo" in r.stderr)

        print("case 3: the old -C form still works (no regression)")
        team2 = root / "my-lib"
        make_repo(team2, "mylib body")
        fire(f"git -C {team2} push", cwd=root, root=root)
        check("my-lib bumped via -C", version_of(team2 / "skills/thing.md") == "1.2.1",
              f"got {version_of(team2 / 'skills/thing.md')}")

        print("case 5: --reconcile catches a body that moved after its version")
        # The out-of-harness case: a commit lands and is PUSHED without the hook
        # ever running, so @{u}..HEAD is empty afterwards and the outgoing range
        # can no longer reveal it. Only git history still can.
        recon = root / "reconcile-me"
        make_repo(recon, "first body")
        git(recon, "push", "-q")                      # pushed WITHOUT the gate
        v0 = version_of(recon / "skills/thing.md")
        f = recon / "skills/thing.md"
        f.write_text(f.read_text().replace("first body", "second body"), encoding="utf-8")
        git(recon, "add", "-A")
        git(recon, "commit", "-qm", "body moves again, still no version bump")
        git(recon, "push", "-q")
        r = run(sys.executable, str(GATE), "--reconcile", str(recon), "--dry-run")
        found = json.loads(r.stdout)["bumped"]
        check("dry-run reports the stale file", any(b["path"].endswith("thing.md") for b in found),
              f"got {found}")
        check("dry-run wrote NOTHING", version_of(f) == v0, f"got {version_of(f)}")

        run(sys.executable, str(GATE), "--reconcile", str(recon))
        check("apply bumped it", version_of(f) != v0, f"{v0} -> {version_of(f)}")
        check("apply committed it", "chore(version)" in git(recon, "log", "--format=%s", "-1").stdout)

        r2 = run(sys.executable, str(GATE), "--reconcile", str(recon), "--dry-run")
        check("second pass is idempotent", json.loads(r2.stdout)["bumped"] == [])

        print("case 4: a push with nothing outgoing changes nothing")
        v_before = version_of(team / "skills/thing.md")
        git(team, "push", "-q")
        fire(f"cd {team} && git push", cwd=team, root=root)
        check("no phantom bump on an empty range",
              version_of(team / "skills/thing.md") == v_before)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if fails:
        print(f"FAILED: {len(fails)} case(s): {', '.join(fails)}")
        return 1
    print("ok — version_gate resolves the pushed repo and refuses generated artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
