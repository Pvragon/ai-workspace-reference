#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.1
# summary: "PreToolUse guard that DENIES any write, edit, command or MCP call whose input contains a known misspelling of a real person's name (pairs in team-lib/config/name-spellings.yaml). Read-only searches and historical records (memory, transcripts, archives, .jsonl) are exempt."
# created: 2026-10-07
# last_updated: 2026-10-16
# maintainer: your-agent
# ---
"""guard_name_spellings.py — never misspell someone in a way that hurts.

Promotes user_toni-mcgee (importance 8): her name is Toni McGee, and the T-o-n-y spelling
upsets her. The persona-briefing source of the wrong spelling was fixed 2026-09-30, so the
remaining risk is typing it. This blocks it in anything that would be written or sent.

Exempt, so a cleanup sweep can still FIND old occurrences and history is not rewritten:
  - Bash that starts with a read-only search (grep, rg, git grep, git log)
  - paths under agents/<agent>/memory/, transcripts/, _archive(d)/, and *.jsonl
Never raises; any internal error -> allow silently.
"""
import json
import re
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config" / "name-spellings.yaml"
READ_ONLY_CMD = re.compile(r"^\s*(grep|rg|egrep|git\s+(grep|log|show|blame))\b")
EXEMPT_PATH = re.compile(r"/agents/[^/]+/memory/|/transcripts/|/_archived?/|\.jsonl$")


def load_pairs():
    try:
        import yaml
        return [p for p in (yaml.safe_load(CONFIG.read_text()) or []) if p.get("wrong")]
    except Exception:
        return []


def check(tool_name: str, tool_input: dict):
    ti = tool_input or {}
    if tool_name == "Bash" and READ_ONLY_CMD.search(str(ti.get("command", ""))):
        return None
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if path and EXEMPT_PATH.search(path):
        return None
    blob = json.dumps(ti, ensure_ascii=False)
    for p in load_pairs():
        try:
            if re.search(p["wrong"], blob, re.I):
                return f"BLOCKED: name misspelled. Write {p['right']}. {p.get('why', '')} Fix it and retry."
        except re.error:
            continue
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        reason = check(payload.get("tool_name", ""), payload.get("tool_input") or {})
    except Exception:
        return 0
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": reason}}))
    return 0


def run(tool_name: str, tool_input: dict):
    return check(tool_name, tool_input)


if __name__ == "__main__":
    sys.exit(main())
