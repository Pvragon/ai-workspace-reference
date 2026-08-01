#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
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


def run(session: str | None = None, project: str | None = None) -> dict:
    """Return the current context usage, or an error dict."""
    proj = Path(project) if project else _project_dir(Path.cwd())
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
    }


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
    print(f"context: {r['used']:,} tokens ({r['pct']}% of {r['window']:,})")
    print(f"  input {r['input_tokens']:,} + cache_read {r['cache_read']:,} "
          f"+ cache_creation {r['cache_creation']:,}")
    print(f"  session {r['session']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
