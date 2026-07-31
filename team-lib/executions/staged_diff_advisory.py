#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "PreToolUse advisory on `git commit`: prints what is actually staged, and flags
#   staged files that a live peer session is also working in. Mechanises the
#   run-git-diff--cached-before-you-commit rule, which failed twice in one week."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: pvragon
# ---
"""staged_diff_advisory.py — show what is staged, before the commit, unasked.

The rule (AGENTS.md Op#10, feedback_verify-staged-before-commit) says: in shared working
trees run `git diff --cached --stat` immediately before `git commit`, because concurrent
sessions pre-stage files that `git status` will not flag.

It failed twice in one week, both times the same way — not from ignorance, but because it
asks for a voluntary extra command at the exact moment you are focused on the commit
message rather than the file list:

  2026-07-30  45 lines of a peer's work went into a commit; staging an explicit path is
              not protection when a sibling session is editing that same path.
  2026-07-30  a peer's commit swept up this session's uncommitted registry/executions.yaml
              edits — the same collision from the other direction.

So it is no longer voluntary. This prints the staged stat every time, and escalates when a
staged file sits in a repo+branch a live peer shares. It never blocks: co-editing is often
deliberate, and a gate that refuses correct commits gets disabled within a day.
"""
import json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def emit(advisory, hook_event="PreToolUse"):
    """Reach the MODEL, not just the terminal.

    stderr alone shows the human and stops there — the agent about to fan out or commit
    never sees it, and that agent is the entire audience. `hookSpecificOutput`
    `.additionalContext` on stdout is what enters model context; stderr is the human copy.
    Both, always, exit 0. (Pattern taken from session_activity.py, whose peer-collision
    advisory does reach context — which is how this omission was noticed at all.)
    """
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": hook_event, "additionalContext": advisory}}))
    print(advisory, file=sys.stderr)


def sh(args, cwd=None):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=15, cwd=cwd)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def peer_sessions(self_sid=""):
    """Live peers sharing our repo+branch, via the coordination roster.

    The roster includes US. Forgetting that turns every solo commit into a collision
    warning, and a warning that fires when nothing is wrong is one you stop reading —
    which is the precise failure this hook exists to prevent. (Same off-by-self bug as
    machine_load.py's peer count, caught the same evening.) The hook payload carries
    session_id, so we can drop our own row rather than guessing by count.
    """
    for cand in (HERE / "session_activity.py",
                 HERE.parent.parent / "my-lib/executions/session_activity.py"):
        if cand.is_file():
            out = sh([sys.executable, str(cand), "roster"])
            rows = []
            for line in out.splitlines():
                if " live " not in line:
                    continue
                parts = line.split()
                sid = parts[0]
                if self_sid and (self_sid.startswith(sid) or sid.startswith(self_sid[:8])):
                    continue                      # that row is us
                rows.append(parts)
            return rows
    return []


def _shell_only(cmd):
    """Strip message BODIES before pattern-matching the command.

    A commit message is part of the command string. This hook's own fix commit contained
    the words "git add" in its message, and the compound-command detector matched them —
    so it announced a staging step that never happened. Prose about a command is not a
    command; anything scanning a shell string has to remove the parts that are data.

    Removes heredoc bodies (<<'EOF' … EOF) and -m/-F quoted arguments.
    """
    cmd = re.sub(r"<<-?\s*'?(\w+)'?.*?^\1\s*$", " ", cmd, flags=re.DOTALL | re.M)
    cmd = re.sub(r"""-m\s+('([^']*)'|"([^"]*)")""", " -m MSG ", cmd, flags=re.DOTALL)
    return cmd


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    cmd = _shell_only((payload.get("tool_input") or {}).get("command", ""))
    # Only real commits. `git commit` inside a heredoc/message body is still a commit, but
    # `git log`/`git show` mentioning the word is not.
    if not re.search(r"\bgit\s+(-\S+\s+)*commit\b", cmd):
        return 0
    if "--dry-run" in cmd:
        return 0

    stat = sh(["git", "diff", "--cached", "--stat"])
    if not stat:
        return 0                      # nothing staged, or not a repo — say nothing

    files = [l.strip().split()[0] for l in sh(["git", "diff", "--cached", "--name-only"]).splitlines() if l.strip()]
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    repo = Path(sh(["git", "rev-parse", "--show-toplevel"]) or ".").name

    # A PreToolUse hook runs BEFORE its command. When the command both stages and commits
    # (`git add … && git commit …` — which is how commits are actually written here, and
    # what the docs show), everything below predates that `git add`, so the list is the
    # PREVIOUS staged set. Observed 2026-07-31: reported 2 files for a commit that landed 3.
    #
    # Under-reporting is the dangerous direction — it shows a smaller, tidier set than what
    # lands, which is exactly the reassurance this hook exists to withhold. It cannot be
    # fixed by measuring harder (the add has not happened yet), so it is labelled instead.
    stages_too = re.search(r"\bgit\s+(-\S+\s+)*(add|stage)\b", cmd)
    if stages_too:
        lines = ["📋 Staged BEFORE this command's own `git add` — the commit may include more:"]
    else:
        lines = ["📋 Staged for this commit:"]
    lines += ["   " + l for l in stat.splitlines()]
    if stages_too:
        lines.append("   ⚠ To see the true set, run `git add` and `git commit` as separate calls.")

    peers = [r for r in peer_sessions(payload.get("session_id", "")) if len(r) > 2 and r[2] == f"{repo}@{branch}"]
    if peers:
        lines.append(f"⚠ {len(peers)} live peer session(s) share {repo}@{branch}: "
                     + ", ".join(r[0] for r in peers))
        lines.append("   Staging an explicit path is NOT protection — a peer editing the same")
        lines.append("   file has its changes in your working tree, and therefore in `git add`.")
        lines.append("   Confirm every file above is yours before committing.")
    elif len(files) > 12:
        lines.append(f"   ({len(files)} files — larger than a typical scoped commit; check it is one logical change.)")

    emit("\n".join(lines))
    return 0


def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
