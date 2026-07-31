#!/usr/bin/env python3
# ---
# template: execution
# version: 1.2.0
# summary: "Reads a Claude Code session JSONL (plus its subagent JSONLs), extracts unique file paths from Edit/Write/MultiEdit/NotebookEdit tool calls, classifies them by repo (my-lib / agents / other), filters to currently-existing files, and drops gitignored paths. Used by postflight to auto-derive --mylib-files / --agents-files instead of requiring the LLM to track them manually. v1.2.0 adds gitignore filtering (runtime/.tmp scratch files no longer break git add)."
# created: 2026-04-30
# last_updated: 2026-04-30
# maintainer: the-operator
# ---
"""
extract_touched_files.py — Auto-derive `git add` paths from a session JSONL.

Replaces the manual Phase 2h burden where the LLM had to track every file it
edited. Reads the JSONL directly, finds Edit/Write/MultiEdit/NotebookEdit tool
calls, classifies the file_path by repo, and outputs JSON.

Usage:
  python3 extract_touched_files.py --session-id <uuid>
  python3 extract_touched_files.py --jsonl <path>
  python3 extract_touched_files.py --session-id <uuid> --mylib /path --agents /path

Output (JSON to stdout):
  {
    "mylib": ["repo-relative/path/a.md", ...],
    "agents": ["memory/foo.md", ...],
    "other": ["/abs/path/outside-known-repos.txt", ...]
  }

Defaults: my-lib at $HOME/ai-workspace/my-lib; agents at
$HOME/ai-workspace/agents/your-agent. Override with --mylib / --agents.

JSONL parsing:
  Each line is a JSON object. Assistant messages contain a `message` field
  whose value is a *stringified* dict (Python repr or JSON depending on era).
  We try json.loads first, fall back to ast.literal_eval. Then we walk
  message.content[] for tool_use blocks with name in EDITING_TOOLS.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

EDITING_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
HOME = Path(os.path.expanduser("~"))
DEFAULT_MYLIB = HOME / "ai-workspace" / "my-lib"
DEFAULT_AGENTS = HOME / "ai-workspace" / "agents" / "your-agent"
PROJECTS_ROOT = HOME / ".claude" / "projects"


def parse_message_field(raw: Any) -> dict | list | None:
    """The `message` field is sometimes a JSON string, sometimes a Python repr.

    Try JSON first; fall back to ast.literal_eval. Return None on failure.
    """
    if isinstance(raw, dict) or isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None


def extract_file_paths_from_message(msg: dict) -> Iterable[str]:
    """Walk a parsed assistant message dict and yield file_path values from Edit-class tool calls."""
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        if block.get("name") not in EDITING_TOOLS:
            continue
        input_obj = block.get("input")
        if not isinstance(input_obj, dict):
            continue
        # Edit/Write/NotebookEdit use file_path; MultiEdit uses file_path too
        path = input_obj.get("file_path") or input_obj.get("notebook_path")
        if isinstance(path, str) and path:
            yield path


def find_jsonl(session_id: str) -> Path | None:
    """Locate the session JSONL across all project dirs."""
    for project_dir in PROJECTS_ROOT.glob("*/"):
        candidate = project_dir / f"{session_id}.jsonl"
        if candidate.is_file():
            return candidate
    return None


def find_subagent_jsonls(parent_jsonl: Path) -> list[Path]:
    """Locate all subagent JSONLs spawned from this parent session.

    Subagents have separate JSONLs at <project-dir>/<session-id>/subagents/agent-*.jsonl.
    The parent session's JSONL only records `Task` tool_use blocks for spawning, not the
    file edits the subagent itself made. Walking these is necessary for postflight to
    auto-stage subagent writes.
    """
    session_id = parent_jsonl.stem  # filename without .jsonl
    subagents_dir = parent_jsonl.parent / session_id / "subagents"
    if not subagents_dir.is_dir():
        return []
    return sorted(p for p in subagents_dir.glob("agent-*.jsonl") if p.is_file())


def classify(path_str: str, mylib: Path, agents: Path) -> tuple[str, str]:
    """Return (bucket, repo_relative_or_absolute_path).

    bucket is one of: 'mylib', 'agents', 'other'.
    For 'other', the original (absolute or as-given) path is returned.
    """
    try:
        path = Path(path_str).resolve()
    except (OSError, RuntimeError):
        return "other", path_str

    try:
        rel = path.relative_to(mylib)
        return "mylib", str(rel)
    except ValueError:
        pass
    try:
        rel = path.relative_to(agents)
        return "agents", str(rel)
    except ValueError:
        pass
    return "other", path_str


def _scan_jsonl_for_paths(jsonl: Path, seen_mylib: set[str], seen_agents: set[str], seen_other: set[str], mylib: Path, agents: Path) -> None:
    """Scan a single JSONL (parent or subagent) and add discovered paths to the bucket sets."""
    with open(jsonl, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "assistant":
                continue
            # NOTE: we no longer skip sidechain at the top level — when scanning a subagent
            # JSONL directly (not via the parent's stream), every entry is sidechain by nature.
            # The parent-vs-subagent distinction is now made by which file we're reading.

            msg = parse_message_field(obj.get("message"))
            if not isinstance(msg, dict):
                continue

            for path_str in extract_file_paths_from_message(msg):
                bucket, normalized = classify(path_str, mylib, agents)
                target = {"mylib": seen_mylib, "agents": seen_agents, "other": seen_other}[bucket]
                target.add(normalized)


def _git_ignored(repo_root: Path, paths: list[str]) -> set[str]:
    """Return the subset of paths (repo-relative) that git would ignore.

    Uses `git -C <repo_root> check-ignore --stdin` for batch efficiency. Returns
    empty set on any failure (treat as nothing-ignored — safer than dropping
    real edits).
    """
    if not paths:
        return set()
    try:
        import subprocess
        result = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "--stdin"],
            input="\n".join(paths),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        # check-ignore exits 0 if ANY paths matched; ignored paths printed line-by-line
        if result.returncode in (0, 1):
            return {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return set()


def extract(jsonl: Path, mylib: Path, agents: Path, include_subagents: bool = True) -> dict:
    """Stream the JSONL (and optionally subagent JSONLs) and bucket all touched file paths.

    Filters output to:
    1. Currently-existing files (paths renamed/deleted mid-session would break `git add`).
    2. Non-gitignored paths (avoids staging scratch files in `runtime/.tmp/` etc.).
    """
    seen_mylib: set[str] = set()
    seen_agents: set[str] = set()
    seen_other: set[str] = set()

    # Scan the parent session JSONL
    _scan_jsonl_for_paths(jsonl, seen_mylib, seen_agents, seen_other, mylib, agents)

    # Scan subagent JSONLs spawned from this session — their edits don't appear in the
    # parent JSONL, so postflight needs to walk them too to auto-stage their writes.
    if include_subagents:
        for sub_jsonl in find_subagent_jsonls(jsonl):
            _scan_jsonl_for_paths(sub_jsonl, seen_mylib, seen_agents, seen_other, mylib, agents)

    # Filter 1: currently-existing paths.
    def _existing_mylib(p: str) -> bool:
        return (mylib / p).exists()

    def _existing_agents(p: str) -> bool:
        return (agents / p).exists()

    def _existing_other(p: str) -> bool:
        try:
            return Path(p).exists()
        except OSError:
            return False

    mylib_existing = [p for p in seen_mylib if _existing_mylib(p)]
    agents_existing = [p for p in seen_agents if _existing_agents(p)]
    other_existing = [p for p in seen_other if _existing_other(p)]

    # Filter 2: drop gitignored paths (e.g., runtime/.tmp/*).
    mylib_ignored = _git_ignored(mylib, mylib_existing)
    agents_ignored = _git_ignored(agents, agents_existing)

    return {
        "mylib": sorted(p for p in mylib_existing if p not in mylib_ignored),
        "agents": sorted(p for p in agents_existing if p not in agents_ignored),
        "other": sorted(other_existing),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--session-id", help="Session UUID; locate JSONL under ~/.claude/projects/*/")
    group.add_argument("--jsonl", type=Path, help="Path to session JSONL directly")
    parser.add_argument("--mylib", type=Path, default=DEFAULT_MYLIB, help=f"my-lib repo root (default: {DEFAULT_MYLIB})")
    parser.add_argument("--agents", type=Path, default=DEFAULT_AGENTS, help=f"agents repo root (default: {DEFAULT_AGENTS})")
    parser.add_argument("--format", choices=["json", "shell"], default="json",
                        help="Output format. 'shell' emits MYLIB_FILES=\"...\" AGENTS_FILES=\"...\" for eval'ing.")
    args = parser.parse_args()

    if args.jsonl:
        jsonl = args.jsonl
        if not jsonl.is_file():
            print(f"ERROR: JSONL not found: {jsonl}", file=sys.stderr)
            return 2
    else:
        jsonl = find_jsonl(args.session_id)
        if jsonl is None:
            print(f"ERROR: no JSONL found for session-id {args.session_id} under {PROJECTS_ROOT}/*/", file=sys.stderr)
            return 2

    result = extract(jsonl, args.mylib.resolve(), args.agents.resolve())

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        # Shell-eval'able. Quote with single quotes; paths shouldn't contain them.
        mylib_files = " ".join(p for p in result["mylib"] if "'" not in p)
        agents_files = " ".join(p for p in result["agents"] if "'" not in p)
        print(f"MYLIB_FILES='{mylib_files}'")
        print(f"AGENTS_FILES='{agents_files}'")
    return 0


def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
