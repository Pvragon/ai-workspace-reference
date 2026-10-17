#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Stop hook: if the reply just written hands the operator a terminal resume command (claude --resume / -r / --continue / -c) and he did not ask for a terminal or shell form, blocks the stop once so the reply is rewritten as /resume <session-id>."
# created: 2026-10-07
# last_updated: 2026-10-07
# maintainer: your-agent
# ---
"""guard_resume_format.py — resume pointers are /resume <id>, never claude --resume.

Promotes feedback_resume-commands-in-slash-format-never-terminal (broken 3 times:
2026-07-02, 2026-09-09, 2026-10-06). the operator runs resumes inline from his open TUI, so a
terminal command is the wrong instruction even when it is technically correct.

On Stop: read transcript_path, take the last assistant message's text and the last real
user prompt. If the text contains a terminal resume command, stop_hook_active is false,
and the prompt does not mention "terminal" or "shell", return decision=block with a
reason; Claude continues and rewrites the reply. stop_hook_active prevents a loop.
Subagent stops (agent_id present) are ignored. Never raises; any error -> allow.
"""
import json
import re
import sys

TERMINAL_RESUME = re.compile(r"\bclaude\s+(--resume|-r|--continue|-c)\b")
ASKED_FOR_TERMINAL = re.compile(r"\b(terminal|shell)\b", re.I)


def _text(msg) -> str:
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    return "\n".join(b.get("text", "") for b in (c or []) if isinstance(b, dict) and b.get("type") == "text")


def last_turn(transcript_path: str):
    """(last assistant text, last real user prompt) from a session JSONL."""
    assistant, user = "", ""
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-400:]
    except OSError:
        return "", ""
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        msg = rec.get("message") or {}
        if not assistant and rec.get("type") == "assistant":
            assistant = _text(msg)
        elif rec.get("type") == "user" and isinstance(msg.get("content"), str):
            user = msg["content"]          # a typed prompt (tool results are lists)
            if assistant:
                break
    return assistant, user


def decide(payload: dict):
    if payload.get("stop_hook_active") or payload.get("agent_id"):
        return None
    assistant, user = last_turn(payload.get("transcript_path", ""))
    if TERMINAL_RESUME.search(assistant) and not ASKED_FOR_TERMINAL.search(user):
        return ("Rewrite the resume pointer as `/resume <full-session-id>`. the operator runs it inline "
                "from his open session; never give `claude --resume` (rule broken 3 times).")
    return None


def main() -> int:
    try:
        reason = decide(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        return 0
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
