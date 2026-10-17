#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.0
# summary: "PreToolUse git guard for shared trees. On `git commit` prints what is staged, the
#   branch, and live peers. Blocks `git stash` (its one deny). Warns before reset/rebase/amend
#   with the last 3 commits, before `git worktree remove` with an untracked/ignored count, and
#   on directory staging or pathspec-less commits while peers are live."
# created: 2026-07-30
# last_updated: 2026-08-01
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

v1.1.0 (2026-10-07) promotes three critical memories into this hook, so they no longer rely
on recall (plan: my-lib/runtime/deliverables/261007-critical-memory-promotion-plan.md):
  - feedback_never-git-stash-in-a-shared-worktree: `git stash` (except list/show) is DENIED.
    This is the hook's single block. The stash stack is shared by every worktree, and a slow
    `stash push -u` deleted a file created mid-run on 2026-09-19.
  - feedback_shared-checkout-commit-and-reset-discipline: warn before reset HEAD~/^, rebase
    and --amend (prints the last 3 commits with authors); warn on `git add -A|.|dir/` and on
    a commit with no ` -- ` pathspec while peers share the branch; always print the branch.
  - feedback_exclusion-rule-is-a-deletion-decision: warn before `git worktree remove` when
    the target holds untracked or ignored entries, which exist nowhere else.
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


GIT = r"\bgit\s+(?:-C\s+\S+\s+|-\S+\s+)*"
STASH_RE = re.compile(GIT + r"stash\b(?!\s+(?:list|show)\b)")
REWRITE_RE = re.compile(GIT + r"(?:reset\b[^|;&]*\bHEAD[~^]|rebase\b|commit\b[^|;&]*--amend\b)")
WT_REMOVE_RE = re.compile(GIT + r"worktree\s+remove\s+(?:-\S+\s+)*(\S+)")
DIR_ADD_RE = re.compile(GIT + r"add\s+(?:[^|;&]*\s)?(?:-A\b|--all\b|\.(?=\s|$)|\S+/(?=\s|$))")

STASH_MSG = ("BLOCKED: git stash is not allowed. The stash stack is shared with every worktree and "
             "peer session, and `stash push -u` over a large untracked tree deleted a file created "
             "mid-run on 2026-09-19. Set work aside with `git commit -qam wip`, then "
             "`git reset --soft HEAD~1`. Compare against a baseline with `git show <sha>:<path>` or "
             "a second worktree. (`git stash list` / `show` are allowed.)")


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    print(reason, file=sys.stderr)


def branch_line():
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if not branch:
        return ""
    primary = sh(["git", "rev-parse", "--git-dir"]) == sh(["git", "rev-parse", "--git-common-dir"])
    return f"branch: {branch}" + (" (primary checkout)" if primary else "")


def shared_peers(payload):
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    repo = Path(sh(["git", "rev-parse", "--show-toplevel"]) or ".").name
    return [r for r in peer_sessions(payload.get("session_id", ""))
            if len(r) > 2 and r[2] == f"{repo}@{branch}"]


def other_git_guards(cmd, payload):
    """Stash / history-rewrite / worktree-remove / directory-add. True if it emitted."""
    if STASH_RE.search(cmd):
        deny(STASH_MSG)
        return True
    if REWRITE_RE.search(cmd):
        lines = ["⚠ Before rewriting history: HEAD~1 may be a peer's commit. Last 3 commits:"]
        lines += ["   " + l for l in sh(["git", "log", "--oneline", "-3", "--format=%h %an %s"]).splitlines()]
        bl = branch_line()
        if bl:
            lines.append("   " + bl)
        peers = shared_peers(payload)
        if peers:
            lines.append(f"   {len(peers)} live peer(s) share this branch: " + ", ".join(r[0] for r in peers))
        lines.append("   Confirm HEAD is yours. In a shared tree a cosmetic mess is cheaper than history surgery.")
        emit("\n".join(lines))
        return True
    m = WT_REMOVE_RE.search(cmd)
    if m:
        target = m.group(1)
        st = sh(["git", "-C", target, "status", "--porcelain", "--ignored"])
        untracked = sum(1 for l in st.splitlines() if l.startswith("??"))
        ignored = sum(1 for l in st.splitlines() if l.startswith("!!"))
        if untracked or ignored:
            emit(f"⚠ Worktree {target} holds {untracked} untracked and {ignored} ignored entries. "
                 "They exist nowhere else. Move ALL of them out with a MANIFEST before removing. "
                 "Do not filter by size or 'regenerable'; sort the copy afterward.")
            return True
        return False
    if DIR_ADD_RE.search(cmd) and not re.search(GIT + r"commit\b", cmd):
        peers = shared_peers(payload)
        if peers:
            emit(f"⚠ Directory staging while {len(peers)} live peer(s) share this branch "
                 f"({', '.join(r[0] for r in peers)}). Stage explicit files, and commit with "
                 "`git commit -F <msgfile> -- <paths>`, which commits only those paths.")
            return True
    return False


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    cmd = _shell_only((payload.get("tool_input") or {}).get("command", ""))
    if other_git_guards(cmd, payload):
        return 0
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
    bl = branch_line()
    if bl:
        lines.append("   " + bl)
    if stages_too:
        lines.append("   ⚠ To see the true set, run `git add` and `git commit` as separate calls.")

    peers = [r for r in peer_sessions(payload.get("session_id", "")) if len(r) > 2 and r[2] == f"{repo}@{branch}"]
    if peers:
        lines.append(f"⚠ {len(peers)} live peer session(s) share {repo}@{branch}: "
                     + ", ".join(r[0] for r in peers))
        lines.append("   Staging an explicit path is NOT protection — a peer editing the same")
        lines.append("   file has its changes in your working tree, and therefore in `git add`.")
        lines.append("   Confirm every file above is yours before committing.")
        if not re.search(r"\s--\s", cmd):
            lines.append("   Use `git commit -F <msgfile> -- <paths>`: it commits only those paths, and")
            lines.append("   `git add <path>` does not protect you from a peer's pre-staged files.")
    elif len(files) > 12:
        lines.append(f"   ({len(files)} files — larger than a typical scoped commit; check it is one logical change.)")

    emit("\n".join(lines))
    return 0


def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
