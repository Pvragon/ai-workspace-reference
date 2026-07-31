#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.1
# summary: "Claude Code PreToolUse hook that walks the agent's lenses/*.md, parses self-declared triggers (tool_match + path_pattern), and injects matching lens content via stderr — with per-(session, lens) dedup so each lens fires at most once per session. Implements the situational T3 layer (renumbered from T3b on 2026-05-10) per the lenses spec."
# created: 2026-04-30
# last_updated: 2026-05-10
# maintainer: the-operator
# ---
"""
inject_lens.py — Hook script that injects matching lenses via stderr at PreToolUse.

Reads stdin JSON (Claude Code hook contract), walks lens files, matches their
declared triggers against the current tool call, and emits matching lens
bodies to stderr ONCE per (session_id, lens_name) pair.

Hook contract (stdin JSON):
  {
    "tool_name": "Edit",
    "tool_input": {"file_path": "/path/to/file", ...},
    "session_id": "...",
    "cwd": "...",
    ...
  }

Lens schema (frontmatter):
  ---
  name: <slug>
  type: lens
  trigger:
    tool_match: <regex>      # required
    path_pattern: <regex>    # optional
  body_token_cap: <int>      # optional, default 200
  ---

  # Body...

Output: stderr text (lens bodies, separated by blank lines). Always exit 0
(never blocks; lenses are advisory).

Dedup:
  - State file at <agent_home>/runtime/state/lens-state-<session_id>.json
  - Format: {"fired": ["lens_name", ...]}
  - Each lens injects at most once per session_id; subsequent matches skip silently.
  - Stale state files for ended sessions are safe to delete at any time.

v1.1.0 changes (2026-05-05):
  - Added per-(session, lens) dedup. Was firing identical lens body on every
    matching tool call, depositing ~22K tokens of repeat content into a typical
    session's cached prefix.
  - Removed MAX_LENSES_PER_FIRE cap. Dedup organically bounds total per-session
    injections to (number of distinct lenses with matching triggers).

Usage:
  - Wired in ~/.claude/settings.json under hooks.PreToolUse
  - Standalone test: python3 inject_lens.py --self-test
  - Debug: python3 inject_lens.py --debug --tool Edit --path /some/path

Self-test uses an isolated state file under runtime/.tmp/_self_test/ so dedup
behavior is exercised without polluting real session state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

# --- portable path resolution (team-lib) -------------------------------------
# Scripts here are invoked by absolute path from hooks and cron, so the sibling
# module is not importable from cwd. Add our own directory to sys.path first.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import (  # noqa: E402
    memory_dir, meditations_dir, lenses_dir, journal_dir, shortterm_dir,
    state_dir, exec_dir, backlog_dir, agent_home, workspace, TOPIC_PREFIXES,
)
# -----------------------------------------------------------------------------

# Resolved defensively: this is a PreToolUse hook, so an unresolvable agent must
# degrade to "inject nothing", never to an exception.
try:
    DEFAULT_LENSES_DIR = lenses_dir()
    DEFAULT_STATE_DIR = state_dir()
except Exception:  # noqa: BLE001 - a hook must not raise
    DEFAULT_LENSES_DIR = Path("/nonexistent")
    DEFAULT_STATE_DIR = Path("/nonexistent")
DEFAULT_BODY_TOKEN_CAP = 200

# Approximate chars-per-token; rough enough for truncation purposes.
CHARS_PER_TOKEN = 4


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-style frontmatter from a markdown file.

    Returns (frontmatter_dict, body). Returns ({}, text) if no frontmatter.
    Hand-rolled (no PyYAML dep) — handles flat keys + one-level-nested keys.
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    raw_fm, body = parts[1], parts[2]
    fm: dict[str, Any] = {}
    current_section: str | None = None
    for line in raw_fm.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        # Top-level key: optional indent of 0, no leading 2-space indent
        if not line.startswith("  "):
            if ":" in line:
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if val == "" or val == "{}":
                    # Section header (e.g., "trigger:")
                    fm[key] = {}
                    current_section = key
                else:
                    fm[key] = _coerce(val)
                    current_section = None
        else:
            # Indented key inside a section
            if current_section and ":" in line:
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                fm[current_section][key] = _coerce(val)
    return fm, body.lstrip("\n")


def _coerce(val: str) -> Any:
    """Strip quotes, coerce to int/bool when obvious."""
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    if val.startswith("'") and val.endswith("'"):
        return val[1:-1]
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    try:
        return int(val)
    except ValueError:
        pass
    return val


def lens_matches(fm: dict[str, Any], tool_name: str, file_path: str | None) -> bool:
    """Return True if the lens's triggers match the current tool call."""
    trigger = fm.get("trigger") or {}
    tool_match_pat = trigger.get("tool_match", "")
    path_pat = trigger.get("path_pattern", "")

    if not tool_match_pat:
        return False
    try:
        if not re.fullmatch(tool_match_pat, tool_name or ""):
            return False
    except re.error:
        return False

    if path_pat:
        if not file_path:
            return False
        try:
            if not re.search(path_pat, file_path):
                return False
        except re.error:
            return False

    return True


def truncate_body(body: str, token_cap: int) -> str:
    """Truncate body to roughly `token_cap` tokens, preserving structure."""
    char_cap = token_cap * CHARS_PER_TOKEN
    if len(body) <= char_cap:
        return body.rstrip()
    truncated = body[:char_cap].rstrip()
    return f"{truncated}\n…[truncated to ~{token_cap} tokens]"


# --- Session-dedup state ---------------------------------------------------

def state_file_path(state_dir: Path, session_id: str) -> Path:
    """Return the per-session state file path."""
    # session_id should already be safe (UUID-ish), but defensively sanitize.
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", session_id or "unknown")
    return state_dir / f"lens-state-{safe}.json"


def load_fired(state_path: Path) -> set[str]:
    """Load the set of already-fired lens names for this session."""
    try:
        if state_path.is_file():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return set(data.get("fired", []))
    except (OSError, json.JSONDecodeError):
        pass
    return set()


def save_fired(state_path: Path, fired: set[str]) -> None:
    """Atomically write fired-lens state. Best-effort: errors are silent."""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp sibling then rename — atomic on POSIX.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8",
            dir=state_path.parent,
            prefix=state_path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            json.dump({"fired": sorted(fired)}, tmp, indent=2)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, state_path)
    except OSError:
        # Best-effort: if state write fails, lens still injects (acceptable
        # — duplicates are the failure mode we're trying to avoid, but a
        # single duplicate from a state-write race is preferable to blocking
        # the tool fire).
        pass


# --- Lens collection -------------------------------------------------------

def collect_matching_lenses(
    lenses_dir: Path,
    tool_name: str,
    file_path: str | None,
    already_fired: set[str] | None = None,
) -> list[tuple[Path, str, int, str]]:
    """Walk lens files, return list of (path, name, token_cap, body) for matches.

    Skips lenses whose name is already in `already_fired` (per-session dedup).
    No upper cap on number of returned lenses — dedup organically bounds it
    to "lenses with first-time matching triggers this session."
    """
    matches: list[tuple[Path, str, int, str]] = []
    if not lenses_dir.is_dir():
        return []
    fired = already_fired or set()

    for lens_file in sorted(lenses_dir.glob("*.md")):
        if lens_file.name == "README.md":
            continue
        try:
            text = lens_file.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body = parse_frontmatter(text)
        if fm.get("type") != "lens":
            continue
        name = fm.get("name", lens_file.stem)
        if name in fired:
            continue
        if not lens_matches(fm, tool_name, file_path):
            continue
        token_cap = int(fm.get("body_token_cap") or DEFAULT_BODY_TOKEN_CAP)
        matches.append((lens_file, name, token_cap, body))

    return matches


def emit_to_stderr(matches: list[tuple[Path, str, int, str]]) -> None:
    """Emit matching lens bodies to stderr in a clear format."""
    if not matches:
        return
    print("=== Lens(es) triggered ===", file=sys.stderr)
    for _path, name, cap, body in matches:
        truncated = truncate_body(body, cap)
        print(f"\n--- LENS: {name} ---", file=sys.stderr)
        print(truncated, file=sys.stderr)
    print("=== /Lens(es) ===", file=sys.stderr)


def read_hook_input() -> dict[str, Any]:
    """Read and parse the stdin JSON from Claude Code hook contract."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--lenses-dir", type=Path, default=DEFAULT_LENSES_DIR,
                        help=f"Directory of lens files (default: {DEFAULT_LENSES_DIR})")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR,
                        help=f"Directory for per-session dedup state files (default: {DEFAULT_STATE_DIR})")
    parser.add_argument("--debug", action="store_true",
                        help="Use --tool/--path/--session instead of stdin; print matches to stdout; do not write state")
    parser.add_argument("--tool", help="(debug) tool_name to simulate")
    parser.add_argument("--path", help="(debug) file_path to simulate")
    parser.add_argument("--session", help="(debug) session_id to simulate (default: 'debug')")
    parser.add_argument("--self-test", action="store_true",
                        help="Run a built-in test against the seed lenses")
    args = parser.parse_args()

    if args.self_test:
        return _self_test(args.lenses_dir)

    if args.debug:
        tool_name = args.tool or ""
        file_path = args.path
        session_id = args.session or "debug"
        write_state = False
    else:
        hook_input = read_hook_input()
        tool_name = hook_input.get("tool_name", "")
        file_path = (hook_input.get("tool_input") or {}).get("file_path")
        session_id = hook_input.get("session_id") or "unknown"
        write_state = True

    # Load already-fired lenses for this session
    state_path = state_file_path(args.state_dir, session_id)
    already_fired = load_fired(state_path)

    matches = collect_matching_lenses(args.lenses_dir, tool_name, file_path, already_fired)

    if args.debug:
        print(f"Tool: {tool_name}\nPath: {file_path}\nSession: {session_id}\nAlready fired: {sorted(already_fired)}\nNew matches: {len(matches)}")
        for _p, name, _c, _b in matches:
            print(f"  - {name}")
        return 0

    if matches:
        emit_to_stderr(matches)
        if write_state:
            already_fired.update(name for _p, name, _c, _b in matches)
            save_fired(state_path, already_fired)
    return 0


def _self_test(lenses_dir: Path) -> int:
    """Built-in self-test against seed lenses, including dedup behavior."""
    # Use an isolated temp state dir so the test doesn't pollute real sessions.
    test_state_dir = DEFAULT_STATE_DIR / "_self_test"
    test_session = "self-test-session"
    test_state_path = state_file_path(test_state_dir, test_session)
    # Clean prior test state
    try:
        if test_state_path.is_file():
            test_state_path.unlink()
    except OSError:
        pass

    # Self-test currently exercises the storage-patterns lens (the only seed lens
    # post-2026-05-05 graduation of session-economics back to AGENTS.md).
    # If a future lens is added that triggers on Bash, extend Phase A/B accordingly.

    # Phase A: cold-state trigger matching (no dedup state yet)
    phase_a_cases = [
        ("Edit", "/tmp/ws/my-lib/skills/foo/SKILL.md", ["storage-patterns"]),
        ("Write", "/tmp/ws/my-lib/executions/foo.py", ["storage-patterns"]),
        ("MultiEdit", "/tmp/ws/agents/example/lenses/foo.md", ["storage-patterns"]),
        ("Bash", None, []),  # No Bash-triggered lens after session-economics graduated to AGENTS.md
        ("Read", "/tmp/ws/my-lib/skills/foo/SKILL.md", []),
        ("Edit", "/tmp/ws/some/random/file.txt", []),
    ]
    failures = 0
    print("Phase A: trigger matching (no dedup state)")
    for tool, path, expected_names in phase_a_cases:
        matches = collect_matching_lenses(lenses_dir, tool, path, already_fired=set())
        actual = sorted(name for (_p, name, _c, _b) in matches)
        expected = sorted(expected_names)
        ok = actual == expected
        marker = "✓" if ok else "✗"
        print(f"  {marker} tool={tool} path={path}: matched {actual} (expected {expected})")
        if not ok:
            failures += 1

    # Phase B: dedup behavior — record fires and verify subsequent matching calls skip
    print("\nPhase B: dedup state suppresses re-fire")
    fired: set[str] = set()

    # First Edit on a skill path → storage-patterns fires
    matches = collect_matching_lenses(
        lenses_dir, "Edit",
        "/tmp/ws/my-lib/skills/foo/SKILL.md",
        already_fired=fired,
    )
    names1 = sorted(n for _p, n, _c, _b in matches)
    fired.update(names1)
    ok1 = names1 == ["storage-patterns"]
    print(f"  {'✓' if ok1 else '✗'} 1st Edit (skill path): {names1} (expected ['storage-patterns'])")
    failures += 0 if ok1 else 1

    # Second Edit on a different skill path → already fired, should skip
    matches = collect_matching_lenses(
        lenses_dir, "Edit",
        "/tmp/ws/my-lib/skills/bar/SKILL.md",
        already_fired=fired,
    )
    names2 = sorted(n for _p, n, _c, _b in matches)
    ok2 = names2 == []
    print(f"  {'✓' if ok2 else '✗'} 2nd Edit (different skill path): {names2} (expected [])")
    failures += 0 if ok2 else 1

    # Write to executions/ should ALSO be suppressed (same lens, different path)
    matches = collect_matching_lenses(
        lenses_dir, "Write",
        "/tmp/ws/my-lib/executions/baz.py",
        already_fired=fired,
    )
    names3 = sorted(n for _p, n, _c, _b in matches)
    ok3 = names3 == []
    print(f"  {'✓' if ok3 else '✗'} Write to executions (same lens fired): {names3} (expected [])")
    failures += 0 if ok3 else 1

    # Edit to a non-matching path → no fire either way (irrelevant to dedup)
    matches = collect_matching_lenses(
        lenses_dir, "Edit",
        "/tmp/ws/some/random/file.txt",
        already_fired=fired,
    )
    names4 = sorted(n for _p, n, _c, _b in matches)
    ok4 = names4 == []
    print(f"  {'✓' if ok4 else '✗'} Edit to non-matching path: {names4} (expected [])")
    failures += 0 if ok4 else 1

    # Phase C: state file roundtrip
    print("\nPhase C: state file persists and reloads")
    save_fired(test_state_path, fired)
    reloaded = load_fired(test_state_path)
    ok5 = reloaded == fired
    print(f"  {'✓' if ok5 else '✗'} save/load roundtrip: {sorted(reloaded)} == {sorted(fired)}")
    failures += 0 if ok5 else 1
    # Cleanup test state
    try:
        if test_state_path.is_file():
            test_state_path.unlink()
        if test_state_dir.is_dir():
            test_state_dir.rmdir()
    except OSError:
        pass

    print(f"\n{'PASS' if failures == 0 else f'FAIL ({failures} cases)'}")
    return 0 if failures == 0 else 1


def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
