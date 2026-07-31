#!/usr/bin/env python3
# ---
# template: execution-script
# version: 1.1.0
# summary: PreToolUse hook that auto-allows Edit/Write/MultiEdit to agent/project
#   memory files AND session-rotation handoff briefs (handoffs/ dirs) so memory,
#   session-debrief, and /handoff saves NEVER trigger a permission prompt —
#   independent of permission mode and cwd. Matches by os.path.realpath under
#   ~/ai-workspace (or ~/.claude/projects) with a memory/ or handoffs/ path
#   segment. Returns the current PreToolUse "allow" decision (short-circuits the
#   permission-mode + ask-rule checks); defers silently (exit 0, no output)
#   otherwise so it never over-broadens. NOTE: it does NOT rescue writes under
#   the PROTECTED ~/.claude/ tree — that prompt fires before allow takes effect,
#   so callers must target canonical non-.claude paths (verified 2026-06-25).
#   Registered in ~/.claude/settings.json under hooks.PreToolUse.
# created: 2026-06-25
# last_updated: 2026-06-25
# maintainer: pvragon
# ---
"""Auto-allow memory-file writes during debrief / memory capture.

Root cause this fixes (verified 2026-06-25 against Claude Code docs): `.claude/`
is a PROTECTED directory. `permissions.allow` rules do NOT pre-approve writes
there, so writing memory via the `~/.claude/projects/<cwd>/memory` symlink alias
prompts on every Edit/Write regardless of an explicit allow rule — and the only
thing that overrides a protected-path prompt is the SESSION permission mode
(bypassPermissions), which is too broad and is not reliably inherited by
in-process teammates. A PreToolUse hook, however, runs FIRST in the permission
pipeline and an "allow" decision short-circuits the protected-dir check, the
mode check, and ask-rules. So this hook makes memory writes frictionless in any
mode, from any cwd, via either path form, for both the main agent and in-process
teammates.

Stdin (from Claude Code): {"tool_name": "...", "tool_input": {"file_path": "..."}}
Stdout on match: {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                          "permissionDecision": "allow"}}
Always exits 0. Any error => defer (no output) so normal permission flow applies.
"""
import json
import os
import sys
from pathlib import Path

# --- portable path resolution (team-lib) -------------------------------------
# Scripts here are invoked by absolute path from hooks and cron, so the sibling
# module is not importable from cwd. Add our own directory to sys.path first.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import (  # noqa: E402
    memory_dir, meditations_dir, lenses_dir, journal_dir, shortterm_dir,
    state_dir, exec_dir, backlog_dir, agent_home, workspace, TOPIC_PREFIXES,
)
# -----------------------------------------------------------------------------
try:
    _WORKSPACE = workspace()
except Exception:  # noqa: BLE001 - a hook must not raise
    _WORKSPACE = Path.home() / 'ai-workspace'

# Safe roots under which a "/memory/" path is treated as an agent/project memory
# file eligible for auto-allow. Bounded on purpose: we never auto-allow a random
# system path that merely happens to contain "/memory/".
SAFE_ROOTS = (
    os.path.realpath(str(_WORKSPACE)),
    os.path.realpath(os.path.expanduser("~/.claude/projects")),
)

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _is_memory_target(file_path: str) -> bool:
    if not file_path:
        return False
    # realpath resolves the .claude/projects/<cwd>/memory symlink alias to the
    # canonical agents/project memory dir AND resolves relative paths against cwd.
    real = os.path.realpath(file_path)
    under_safe_root = any(
        real == root or real.startswith(root + os.sep) for root in SAFE_ROOTS
    )
    if not under_safe_root:
        return False
    # Must live in a `memory` dir (MEMORY.md, current-state.md, session-log.md,
    # short-term/*, project_*/reference_* topic files) OR a `handoffs` dir
    # (session-rotation briefs from /handoff + /create-handoff-docs).
    parts = real.split(os.sep)
    return "memory" in parts or "handoffs" in parts


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # unparseable -> defer to normal permission flow

    tool = data.get("tool_name") or data.get("tool") or ""
    if tool not in EDIT_TOOLS:
        sys.exit(0)

    tool_input = data.get("tool_input") or data.get("input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""

    if _is_memory_target(file_path):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": (
                    "agent memory/handoff write — pre-approved by "
                    "allow_memory_writes PreToolUse hook"
                ),
            }
        }))
    sys.exit(0)


if __name__ == "__main__":
    main()
