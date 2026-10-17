#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.3
# summary: >-
#   PostToolUse hook that regenerates the public reference repo whenever team-lib is pushed, so
#   the published layer is never stale by more than one push. Commits the result in the public
#   repo but never pushes — that stays a human decision. Refuses to publish a leak, never blocks
#   a push, and shares version_gate's repo resolution.
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
    if not fired:
        print("  NOTE: registered and firing, but no team-lib push has happened yet.")
    for ln in lines[-5:]:
        print("  " + ln)
    return 0


def publish_now(quiet: bool = False) -> int:
    """Regenerate the public repo and commit it. Returns files written, -1 on refusal.

    The single implementation, shared by the push hook and the nightly tick. The tick
    is the safety net the hook cannot be: a push made from a plain terminal, another
    machine, or any session without this harness fires no hook at all, and the public
    layer would sit stale until someone noticed.
    """
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
        if not quiet:
            print("[publish-gate] PUBLICATION REFUSED — a blocked identifier survived\n"
                  "               generalization. The public repo was NOT updated.\n"
                  + out[-800:], file=sys.stderr)
        return -1

    written = re.search(r"written/updated\s*:\s*(\d+)", out)
    n = int(written.group(1)) if written else 0
    if n == 0 or not run("git", "-C", public, "status", "--porcelain").stdout.strip():
        beat("nothing", "public already current")
        return 0

    run("git", "-C", public, "add", "-A")

    # ⚑ SCRUB WHAT IS COMMITTED, NOT ONLY WHAT WAS WRITTEN.
    #
    # publish_public_reference.py scrubs every file IT writes and refuses on a leak — and that
    # check is sound. But the commit below is `git add -A`, which stages everything in the public
    # working tree, INCLUDING files the publisher never wrote and therefore never scrubbed. The
    # two sets are not the same, and the gap is silent: the publisher reports
    # `refused (leak) : 0` truthfully, about a different set of files than the one being
    # published.
    #
    # Measured 2026-08-27: a publish commit staged `runtime/logs/preflight_bg_snapshot.log` and
    # `preflight_bg_transcripts.log` — background-job output carrying absolute /home/<user>/
    # paths, private project names and live session ids — into the PUBLIC repo, with the gate
    # reporting 0 leaks. Caught only by a human grepping the outgoing diff before pushing.
    # Nothing had leaked (the files were untracked in origin/main), but the only thing between
    # that and publication was someone choosing to look.
    #
    # So re-run the same blocklist over the STAGED DIFF, which is a superset of what the
    # publisher wrote and is exactly what a push would send. Refuse by unstaging: leaving the
    # index populated after refusing would let the next commit in that repo carry it anyway.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import yaml  # noqa: PLC0415
        from publish_public_reference import _blocked  # noqa: PLC0415

        mirror = yaml.safe_load(
            (Path(__file__).resolve().parents[1] / "registry" / "mirror.yaml").read_text())
        pub_cfg = (mirror or {}).get("publication") or {}
        blocklist = [(g, t) for g, ts in (pub_cfg.get("scrub") or {}).items() for t in ts]

        staged_names = run("git", "-C", public, "diff", "--cached", "--name-only").stdout
        # ADDED lines only. A diff also carries the lines it removes, so scanning all of it
        # refused exactly the commit that scrubs a leak (measured 2026-10-16: the cleanup that
        # removed every internal identifier tripped on its own deletions).
        staged_diff = "\n".join(
            ln[1:] for ln in run("git", "-C", public, "diff", "--cached").stdout.splitlines()
            if ln.startswith("+") and not ln.startswith("+++"))
        allow = list(pub_cfg.get("scrub_allow") or [])
        leaked = _blocked(staged_diff, blocklist, allow) + _blocked(staged_names, blocklist, allow)
        if leaked:
            run("git", "-C", public, "reset", "-q")
            beat("refused-staged", f"{len(set(leaked))} identifier(s) in the staged diff")
            if not quiet:
                print("[publish-gate] PUBLICATION REFUSED — blocked identifier(s) in the STAGED\n"
                      "               diff, in files the publisher did not write and so did not\n"
                      "               scrub. Index reset; the public repo was NOT updated.\n"
                      f"               identifiers: {sorted(set(leaked))[:6]}\n"
                      f"               staged files:\n{staged_names}", file=sys.stderr)
            return -1
    except Exception as e:  # noqa: BLE001
        # This gate must never be the reason a publish fails to run at all; a stale mirror is
        # cheaper than a broken hook. But say so — a scrub that silently stopped scrubbing is
        # indistinguishable from one with nothing to find.
        if not quiet:
            print(f"[publish-gate] WARNING: staged-diff scrub did not run ({type(e).__name__}: "
                  f"{e}). Commit proceeding UNVERIFIED — check the diff before pushing.",
                  file=sys.stderr)

    run("git", "-C", public, "commit", "-q", "-m",
        f"chore(publish): regenerate from team-lib ({n} file(s))\n\n"
        "Auto-applied by publish_gate.py. The public repo is a GENERATED artifact —\n"
        "edit team-lib and let this regenerate it. Not pushed: publishing to the\n"
        "world stays a human decision.\n[no-version]")

    ahead = run("git", "-C", public, "rev-list", "--count", "@{u}..HEAD").stdout.strip() or "?"
    beat("published", f"{n} file(s), public now ahead {ahead}")
    if not quiet:
        print(f"[publish-gate] public reference regenerated: {n} file(s) updated and\n"
              f"               committed. NOT pushed — {ahead} commit(s) waiting in\n"
              f"               {public}", file=sys.stderr)
    return n


def main() -> int:
    if "--self-check" in sys.argv:
        return self_check()

    # Invoked directly (the nightly tick), not as a hook: no stdin to read.
    if "--run" in sys.argv:
        n = publish_now(quiet="--quiet" in sys.argv)
        print(json.dumps({"status": "refused" if n < 0 else "ok",
                          "written": max(n, 0)}))
        return 0

    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    if data.get("tool_name") != "Bash":
        return 0
    cmd = (data.get("tool_input") or {}).get("command", "")
    if not re.search(r"\bgit\s+(-C\s+\S+\s+)?push\b", cmd):
        # Log even the no-op case. Without this, "registered but no pushes yet" and
        # "never registered at all" produce an identical (empty) log, and
        # --self-check cannot tell them apart — the liveness question it exists to
        # answer. version_gate beats `not-a-push` for the same reason.
        beat("skip", "not-a-push")
        return 0

    repo = resolve_pushed_repo(cmd, data.get("cwd"))
    # Only a push of the SHARED layer republishes. my-lib is personal and never
    # published; the public repo is the output and must not trigger itself.
    if os.path.realpath(repo) != os.path.realpath(os.path.join(WORKSPACE, SHARED_LAYER)):
        beat("skip", f"not the shared layer: {os.path.basename(repo)}")
        return 0

    publish_now()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # never cost anyone a push
