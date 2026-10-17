#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.1
# summary: "Reports the CURRENT session's context usage by reading the last usage payload out of
#   the session JSONL — the same three fields the statusline sums. Exists because the agent cannot
#   see the context_window payload and its from-conversation-length estimate ran ~40% high, which
#   made every threshold reminder wrong in the alarming direction."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# Why this exists
# ---------------
# AGENTS.md sets context-window thresholds (heads-up at ~400k, standing reminder past ~500k on a
# 1M window) and then says the payload is not injected per-turn, so estimate from conversation
# length. Measured 2026-08-01: the estimate said "around 400k" against a real 287k — high by
# ~40%, and consistently high, so the agent nagged about rotating a session that had two thirds
# of its window left.
#
# That is the shape AGENTS.md already forbids elsewhere: reporting a naive estimate as a result
# without checking it against the correct method. The correct method exists and is cheap — the
# transcript on disk carries the same usage payload the statusline reads. So: measure it.
#
# The number is `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` from the
# most recent assistant message, matching ~/.claude/statusline.sh exactly. Anything else (summing
# turns, counting characters) double-counts the cache and is how the estimate went wrong.
#
# Usage:
#   context_usage.py                  # current session, human-readable
#   context_usage.py --json           # machine-readable
#   context_usage.py --session <id>   # a specific session id
#   context_usage.py --project <dir>  # a specific project transcript dir

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
DEFAULT_WINDOW = 200_000
LONG_WINDOW = 1_000_000


def _project_dir(cwd: Path) -> Path:
    """Claude Code encodes the project cwd as a flat directory name."""
    return PROJECTS / ("-" + str(cwd).strip("/").replace("/", "-"))


def _latest_transcript(project: Path) -> Path | None:
    files = [p for p in project.glob("*.jsonl") if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _last_usage(path: Path) -> dict | None:
    """Last message-level usage block in the transcript.

    Read forward rather than tailing: the final lines are often tool results or
    summaries with no usage, and a naive tail returns nothing on a busy session.
    """
    last = None
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue
            usage = msg.get("usage")
            if isinstance(usage, dict) and "input_tokens" in usage:
                last = usage
    return last


def _result(path: Path, usage: dict, exact: bool) -> dict:
    used = (usage.get("input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0))
    # The window is a property of the model, which the transcript does not state
    # reliably; take the caller's word for it and default to the long window only
    # when explicitly told, so a wrong default cannot understate the percentage.
    window = LONG_WINDOW if os.environ.get("PVRAGON_CONTEXT_WINDOW") == "1m" else DEFAULT_WINDOW
    return {
        "status": "ok",
        "session": path.stem,
        "used": used,
        "input_tokens": usage.get("input_tokens", 0),
        "cache_read": usage.get("cache_read_input_tokens", 0),
        "cache_creation": usage.get("cache_creation_input_tokens", 0),
        "window": window,
        "pct": round(100.0 * used / window, 1),
        # False when the session was GUESSED. Callers must not present a non-exact
        # figure as a measurement.
        "exact": exact,
    }


def _find_by_id(session_id: str) -> Path | None:
    """Locate a session transcript by id across every project directory."""
    for cand in PROJECTS.glob(f"*/{session_id}.jsonl"):
        if cand.is_file():
            return cand
    return None


def run(session: str | None = None, project: str | None = None) -> dict:
    """Return the current context usage, or an error dict.

    Resolution order, most authoritative first:
      1. --session
      2. $CLAUDE_CODE_SESSION_ID — the running session, exact and cwd-independent
      3. the cwd's project dir, most recent transcript
      4. the most recently active project anywhere

    3 and 4 are guesses and say so. They have to be: measured 2026-08-01, FOUR transcripts
    in one project directory shared an mtime to the minute, because concurrent sessions
    share a repo. "Most recent" picked a peer's session and reported its number as mine.
    """
    exact = True
    if not session and not project:
        env_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
        if env_id:
            found = _find_by_id(env_id)
            if found is not None:
                usage = _last_usage(found)
                if usage:
                    return _result(found, usage, exact=True)

    proj = Path(project) if project else _project_dir(Path.cwd())
    if not proj.is_dir() and not project:
        # Run from a directory that is not the session's own project — team-lib, say —
        # and the cwd-derived path does not exist.
        #
        # The first cut silently fell back to the most recently active project and
        # confidently reported a number for a DIFFERENT session (a peer's, measured
        # 2026-08-01). That is the exact shape this whole script exists to eliminate: a
        # probe answering with something plausible when the honest answer is "I do not
        # know which session you mean". The fallback stays, because it is usually right
        # and refusing would be useless — but it is now labelled, and every caller sees
        # `exact: false` rather than a number that looks measured.
        candidates = [d for d in PROJECTS.glob("*") if d.is_dir() and any(d.glob("*.jsonl"))]
        if candidates:
            proj = max(candidates, key=lambda d: max(f.stat().st_mtime for f in d.glob("*.jsonl")))
            exact = False
    if not proj.is_dir():
        return {"status": "error", "error": f"no transcript directory: {proj}"}

    if session:
        path = proj / f"{session}.jsonl"
        if not path.is_file():
            return {"status": "error", "error": f"no transcript for session {session}"}
    else:
        path = _latest_transcript(proj)
        if path is None:
            return {"status": "error", "error": f"no transcripts in {proj}"}

    usage = _last_usage(path)
    if not usage:
        return {"status": "error", "error": f"no usage payload in {path.name}"}
    return _result(path, usage, exact=exact)


def main() -> int:
    ap = argparse.ArgumentParser(description="Report this session's context usage.")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--session", help="session id (default: most recently modified)")
    ap.add_argument("--project", help="transcript directory (default: derived from cwd)")
    args = ap.parse_args()

    r = run(session=args.session, project=args.project)
    if args.json:
        print(json.dumps(r))
        return 0 if r["status"] == "ok" else 1
    if r["status"] != "ok":
        print(f"context_usage: {r['error']}", file=sys.stderr)
        return 1
    if not r.get("exact", True):
        print("WARNING: cwd is not a session project dir — this is the most recently "
              "ACTIVE session, which may be a different one. Pass --session to be sure.",
              file=sys.stderr)
    print(f"context: {r['used']:,} tokens ({r['pct']}% of {r['window']:,})"
          f"{'' if r.get('exact', True) else '   [GUESSED SESSION]'}")
    print(f"  input {r['input_tokens']:,} + cache_read {r['cache_read']:,} "
          f"+ cache_creation {r['cache_creation']:,}")
    print(f"  session {r['session']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
