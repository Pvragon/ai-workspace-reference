#!/usr/bin/env python3
# ---
# template: execution
# version: 1.3.0
# summary: "Claude Code PreToolUse hook that walks the agent's lenses/*.md, parses self-declared triggers (tool_match, then any of path_pattern / command_pattern / content_pattern), and injects matching lens content via stderr — with per-(session, lens) dedup so each lens fires at most once per session. Implements the situational T3 layer (renumbered from T3b on 2026-05-10) per the lenses spec."
# created: 2026-04-30
# last_updated: 2026-08-05
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
    tool_match: <regex>        # required, full-match against tool_name
    path_pattern: <regex>      # optional, searched in file_path / notebook_path / path / url
    command_pattern: <regex>   # optional, searched in a Bash command (message bodies stripped)
    content_pattern: <regex>   # optional, searched in content / new_string / edits[].new_string
  body_token_cap: <int>      # optional, default 200
  ---

  # Body...

Match semantics (v1.3.0): tool_match must match. Then, if any of the three patterns is
declared, AT LEAST ONE declared pattern must match (OR). With none declared, tool_match
alone decides. A lens declaring a single pattern behaves exactly as before v1.3.0.

v1.3.0 changes (2026-10-07):
  - Lenses could see only tool_name and tool_input.file_path, so no lens could fire on
    "Bash running git stash" or "a script that sends DELETE". Added command_pattern and
    content_pattern, and a path fallback (notebook_path, path, url) so Grep/Glob/
    NotebookEdit/browser navigation can match path_pattern. Bash + path_pattern used to be
    a silent never-match; it now matches nothing only because Bash has no path.

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


PATH_KEYS = ("file_path", "notebook_path", "path", "url")


def resolve_path(tool_input: dict[str, Any] | None) -> str | None:
    """First path-like field present in tool_input (file_path, notebook_path, path, url)."""
    for k in PATH_KEYS:
        v = (tool_input or {}).get(k)
        if isinstance(v, str) and v:
            return v
    return None


def strip_message_bodies(cmd: str) -> str:
    """Remove heredoc bodies and -m quoted arguments, so prose ABOUT a command is not a
    command. Same rule as staged_diff_advisory._shell_only (a commit message mentioning
    "git stash" must not fire a git-stash lens)."""
    cmd = re.sub(r"<<-?\s*'?(\w+)'?.*?^\1\s*$", " ", cmd, flags=re.DOTALL | re.M)
    cmd = re.sub(r"""-m\s+('([^']*)'|"([^"]*)")""", " -m MSG ", cmd, flags=re.DOTALL)
    return cmd


def written_content(tool_input: dict[str, Any] | None) -> str:
    """Text a Write/Edit/MultiEdit would put on disk."""
    ti = tool_input or {}
    parts = [ti.get("content"), ti.get("new_string")]
    parts += [e.get("new_string") for e in (ti.get("edits") or []) if isinstance(e, dict)]
    return "\n".join(p for p in parts if isinstance(p, str))


def _search(pat: str, text: str | None) -> bool:
    if not text:
        return False
    try:
        return bool(re.search(pat, text))
    except re.error:
        return False


def lens_matches(fm: dict[str, Any], tool_name: str, file_path: str | None,
                 tool_input: dict[str, Any] | None = None) -> bool:
    """Return True if the lens's triggers match the current tool call.

    tool_match must full-match. Then, if any pattern is declared, at least one declared
    pattern must match (OR). `file_path` is kept for callers that only have a path.
    """
    trigger = fm.get("trigger") or {}
    tool_match_pat = trigger.get("tool_match", "")
    path_pat = trigger.get("path_pattern", "")
    cmd_pat = trigger.get("command_pattern", "")
    content_pat = trigger.get("content_pattern", "")

    if not tool_match_pat:
        return False
    try:
        if not re.fullmatch(tool_match_pat, tool_name or ""):
            return False
    except re.error:
        return False

    declared = [p for p in (path_pat, cmd_pat, content_pat) if p]
    if not declared:
        return True
    path = file_path or resolve_path(tool_input)
    if path_pat and _search(path_pat, path):
        return True
    if cmd_pat and _search(cmd_pat, strip_message_bodies(str((tool_input or {}).get("command") or ""))):
        return True
    if content_pat and _search(content_pat, written_content(tool_input)):
        return True
    return False


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
    tool_input: dict[str, Any] | None = None,
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
        if not lens_matches(fm, tool_name, file_path, tool_input):
            continue
        token_cap = int(fm.get("body_token_cap") or DEFAULT_BODY_TOKEN_CAP)
        matches.append((lens_file, name, token_cap, body))

    return matches


def render_lenses(matches: list[tuple[Path, str, int, str]]) -> str:
    """Render matching lens bodies into the text block shown to the model."""
    parts = ["=== Lens(es) triggered ==="]
    for _path, name, cap, body in matches:
        parts.append(f"\n--- LENS: {name} ---")
        parts.append(truncate_body(body, cap))
    parts.append("=== /Lens(es) ===")
    return "\n".join(parts)


def emit_to_stderr(matches: list[tuple[Path, str, int, str]]) -> None:
    """Emit matching lens bodies to stderr — the HUMAN/transcript copy only.

    stderr does NOT reach the model on an exit-0 PreToolUse hook. Keep this for
    the operator watching the transcript; see emit_for_model() for the real path.
    """
    if not matches:
        return
    print(render_lenses(matches), file=sys.stderr)


def emit_for_model(matches: list[tuple[Path, str, int, str]],
                   hook_event: str = "PreToolUse") -> None:
    """Emit lens bodies where the MODEL will actually receive them.

    Until 2026-08-05 this script only wrote to stderr and exited 0. Per
    https://code.claude.com/docs/en/hooks.md, exit-0 stderr reaches the model on
    PostToolUse alone — everywhere else it is debug/transcript output. So on a
    PreToolUse hook the lens system matched, capped and deduped correctly for
    months while delivering nothing: measured 2026-08-02 by firing
    `subagent-discipline` (2111 B) and `storage-patterns` (918 B) on real tool
    calls and confirming neither reached the model's context.

    `hookSpecificOutput.additionalContext` on stdout is the supported channel for
    PreToolUse (and PostToolUse / UserPromptSubmit / SessionStart / Stop /
    SubagentStop). fanout_load_advisory.py already uses it and demonstrably lands.
    """
    if not matches:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": hook_event,
        "additionalContext": render_lenses(matches),
    }}))


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
    parser.add_argument("--command", help="(debug) Bash command to simulate")
    parser.add_argument("--self-test", action="store_true",
                        help="Run a built-in test against the seed lenses")
    args = parser.parse_args()

    if args.self_test:
        return _self_test(args.lenses_dir)

    if args.debug:
        tool_name = args.tool or ""
        file_path = args.path
        tool_input = {"command": args.command} if args.command else {}
        session_id = args.session or "debug"
        hook_event = "PreToolUse"
        write_state = False
    else:
        hook_input = read_hook_input()
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input") or {}
        file_path = resolve_path(tool_input)
        session_id = hook_input.get("session_id") or "unknown"
        hook_event = hook_input.get("hook_event_name") or "PreToolUse"
        write_state = True

    # Load already-fired lenses for this session
    state_path = state_file_path(args.state_dir, session_id)
    already_fired = load_fired(state_path)

    matches = collect_matching_lenses(args.lenses_dir, tool_name, file_path, already_fired,
                                      tool_input)

    if args.debug:
        print(f"Tool: {tool_name}\nPath: {file_path}\nSession: {session_id}\nAlready fired: {sorted(already_fired)}\nNew matches: {len(matches)}")
        for _p, name, _c, _b in matches:
            print(f"  - {name}")
        return 0

    if matches:
        emit_for_model(matches, hook_event)   # stdout JSON — the model sees this
        emit_to_stderr(matches)               # stderr — human/transcript copy
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

    # Phase D (v1.3.0): command_pattern, content_pattern, path fallback, OR semantics.
    # Synthetic lenses in a throwaway dir, so this does not depend on the live lens set.
    print("\nPhase D: command / content / path-fallback triggers")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "cmd.md").write_text("---\nname: cmd\ntype: lens\ntrigger:\n  tool_match: 'Bash'\n"
                                    "  command_pattern: '\\bgit\\s+stash\\b'\n---\nbody\n")
        (tdp / "content.md").write_text("---\nname: content\ntype: lens\ntrigger:\n  tool_match: 'Edit|Write|MultiEdit'\n"
                                        "  content_pattern: 'requests\\.delete\\('\n---\nbody\n")
        (tdp / "either.md").write_text("---\nname: either\ntype: lens\ntrigger:\n  tool_match: 'Edit|Write|Grep|Bash'\n"
                                       "  path_pattern: '/billing/'\n  command_pattern: 'reconcil'\n---\nbody\n")
        d_cases = [
            ("Bash", {"command": "git stash push -u"}, ["cmd"]),
            ("Bash", {"command": "git commit -m 'never git stash here'"}, []),   # message body stripped
            ("Bash", {"command": "git commit -F - <<'EOF'\ngit stash note\nEOF"}, []),  # heredoc stripped
            ("Write", {"file_path": "/x/a.py", "content": "requests.delete(url)"}, ["content"]),
            ("MultiEdit", {"file_path": "/x/a.py", "edits": [{"new_string": "r = requests.delete(u)"}]}, ["content"]),
            ("Write", {"file_path": "/x/a.py", "content": "requests.get(url)"}, []),
            ("Grep", {"path": "/repo/billing/x"}, ["either"]),                    # path fallback
            ("Bash", {"command": "python3 reconcile.py"}, ["either"]),            # OR: command branch
            ("Edit", {"file_path": "/repo/other/x.py", "new_string": "y"}, []),
        ]
        for tool, ti, expected in d_cases:
            got = sorted(n for _p, n, _c, _b in collect_matching_lenses(
                tdp, tool, None, already_fired=set(), tool_input=ti))
            ok = got == sorted(expected)
            print(f"  {'✓' if ok else '✗'} {tool} {str(ti)[:60]}: {got} (expected {expected})")
            failures += 0 if ok else 1

    print(f"\n{'PASS' if failures == 0 else f'FAIL ({failures} cases)'}")
    return 0 if failures == 0 else 1


def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
