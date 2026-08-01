#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "PostToolUse hook that regenerates the public reference repo whenever team-lib is pushed,
#   so the published layer is never stale by more than one push. Runs publish_public_reference.py,
#   commits the result in the public repo (never pushes — that stays a human decision), and logs a
#   heartbeat. Refuses to publish a leak, never blocks, and shares version_gate's repo resolution so
#   the two push-boundary hooks cannot drift on which repo a command actually targets."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
"""publish_gate.py — keep the public layer current without anyone remembering to.

Why this exists
---------------
Detection existed and publication existed; nothing connected them. `layer_drift_scan`
would report "stale in public" and a human would run `publish_public_reference.py` by
hand. On 2026-08-01 that was six manual runs in one session — and between each of them
the public repo was, briefly, wrong. Syncing was an audit, not a routine.

Why PostToolUse and not PreToolUse
----------------------------------
version_gate runs BEFORE the push and may add a `chore(version)` commit. Publishing
before that lands would ship the pre-bump content and immediately be stale again. So
this runs AFTER the push, when team-lib's state is final.

What it deliberately does NOT do
--------------------------------
It does not push the public repo. Generating is mechanical; publishing to the world
is a decision, and the workspace rule is that push needs a human. It commits so the
change is captured and reviewable, and says so.

Exit status is always 0. A hook that can fail a push is worse than a stale mirror.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from version_gate import (  # noqa: E402  — one implementation of "which repo?"
    PUBLIC_LAYER, WORKSPACE, resolve_pushed_repo,
)

HEARTBEAT = os.path.expanduser("~/.claude/publish-gate.log")
PUBLISHER = Path(__file__).resolve().parent / "publish_public_reference.py"
SHARED_LAYER = "team-lib"


def beat(event: str, detail: str = "") -> None:
    """Log every invocation. A gate that silently stops firing looks exactly like a
    gate with nothing to do — the same reason version_gate keeps a heartbeat."""
    try:
        import datetime
        os.makedirs(os.path.dirname(HEARTBEAT), exist_ok=True)
        with open(HEARTBEAT, "a") as fh:
            fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}\t{event}\t{detail}\n")
    except OSError:
        pass


def run(*args, cwd=None, timeout=180):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def self_check() -> int:
    """Is this hook alive? Mirrors version_gate --self-check."""
    if not os.path.isfile(HEARTBEAT):
        print(f"publish-gate: NO LOG at {HEARTBEAT} — the hook has never run.")
        return 1
    lines = open(HEARTBEAT).read().splitlines()
    fired = [ln for ln in lines if "\tpublished\t" in ln or "\tnothing\t" in ln]
    print(f"publish-gate: {len(lines)} invocation(s) logged, {len(fired)} on a team-lib push")
    for ln in lines[-5:]:
        print("  " + ln)
    return 0


def main() -> int:
    if "--self-check" in sys.argv:
        return self_check()

    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    if data.get("tool_name") != "Bash":
        return 0
    cmd = (data.get("tool_input") or {}).get("command", "")
    if not re.search(r"\bgit\s+(-C\s+\S+\s+)?push\b", cmd):
        return 0

    repo = resolve_pushed_repo(cmd, data.get("cwd"))
    # Only a push of the SHARED layer republishes. my-lib is personal and never
    # published; the public repo is the output and must not trigger itself.
    if os.path.realpath(repo) != os.path.realpath(os.path.join(WORKSPACE, SHARED_LAYER)):
        beat("skip", f"not the shared layer: {os.path.basename(repo)}")
        return 0

    public = os.path.join(WORKSPACE, PUBLIC_LAYER)
    if not os.path.isdir(os.path.join(public, ".git")):
        beat("skip", "public repo not present on this machine")
        return 0

    r = run(sys.executable, str(PUBLISHER), "--apply")
    out = (r.stdout or "") + (r.stderr or "")

    # A refusal means the scrub gate caught an identifier that generalization missed.
    # That is the gate working; surface it loudly rather than burying it in a log.
    refused = re.search(r"refused \(leak\)\s*:\s*(\d+)", out)
    if refused and refused.group(1) != "0":
        beat("refused", f"{refused.group(1)} file(s) blocked by the scrub gate")
        print("[publish-gate] PUBLICATION REFUSED — a blocked identifier survived\n"
              "               generalization. The public repo was NOT updated.\n"
              + out[-800:], file=sys.stderr)
        return 0

    written = re.search(r"written/updated\s*:\s*(\d+)", out)
    n = int(written.group(1)) if written else 0
    if n == 0:
        beat("nothing", "public already current")
        return 0

    if not run("git", "-C", public, "status", "--porcelain").stdout.strip():
        beat("nothing", "publisher wrote nothing git can see")
        return 0

    run("git", "-C", public, "add", "-A")
    run("git", "-C", public, "commit", "-q", "-m",
        f"chore(publish): regenerate from team-lib ({n} file(s))\n\n"
        "Auto-applied by publish_gate.py when team-lib was pushed. The public repo is\n"
        "a GENERATED artifact — edit team-lib and let this regenerate it. Not pushed:\n"
        "publishing to the world stays a human decision.\n[no-version]")

    ahead = run("git", "-C", public, "rev-list", "--count", "@{u}..HEAD").stdout.strip() or "?"
    beat("published", f"{n} file(s), public now ahead {ahead}")
    print(f"[publish-gate] public reference regenerated: {n} file(s) updated and\n"
          f"               committed. NOT pushed — {ahead} commit(s) waiting in\n"
          f"               {public}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # never cost anyone a push
