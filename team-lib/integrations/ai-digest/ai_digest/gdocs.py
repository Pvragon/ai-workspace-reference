"""Create a Google Doc from Markdown via the ``gws`` CLI — no MCP, cron-safe.

Google Workspace is always accessed through ``gws`` (hard rule); MCP is not even
available in the cron environment the poll runs in. ``gws`` owns Google auth, so
we just shell out: ``gws docs documents create`` for a blank doc, then
``gws docs documents batchUpdate`` to insert structured content.

Formatting is intentionally limited to what is RELIABLE via batchUpdate index
math: real heading paragraphs + bullet lists. Inline markdown (bold, links) is
flattened for safety — links render inline as ``text (url)``. Returns the doc's
web URL, or None on any failure (the caller degrades: email still sends, just
without the link).
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Optional

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_HEAD = re.compile(r"^(#{1,6})\s+(.*)")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)")


def _gws(args: list[str], *, body=None, params=None) -> dict:
    cmd = ["gws"] + args
    if params is not None:
        cmd += ["--params", json.dumps(params)]
    if body is not None:
        cmd += ["--json", json.dumps(body)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"_error": str(e)}
    # gws prepends a "Using keyring backend: keyring" banner that breaks JSON parse
    out = "\n".join(l for l in r.stdout.splitlines() if "keyring backend" not in l)
    try:
        return json.loads(out)
    except (ValueError, TypeError):
        return {"_error": (r.stderr or out or "")[:200]}


def _flatten_inline(s: str) -> str:
    s = _LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", s)
    s = _BOLD.sub(lambda m: m.group(1) or m.group(2), s)
    s = _ITALIC.sub(r"\1", s)
    return s.replace("`", "")


_NAMED = {1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3",
          4: "HEADING_4", 5: "HEADING_5", 6: "HEADING_6"}


def markdown_to_doc(title: str, md: str) -> Optional[str]:
    """Create a Google Doc titled ``title`` from ``md``. Returns its URL or None."""
    doc = _gws(["docs", "documents", "create"], body={"title": title})
    doc_id = doc.get("documentId")
    if not doc_id:
        return None

    # Parse markdown into (text, kind) paragraphs. kind: 'h1'..'h6' | 'bullet' | 'normal'
    paras: list[tuple[str, str]] = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            paras.append(("", "normal"))
            continue
        if set(line.strip()) <= {"-", "*", "_"} and len(line.strip()) >= 3:
            paras.append(("", "normal"))          # horizontal rule -> blank line
            continue
        m = _HEAD.match(line)
        if m:
            paras.append((_flatten_inline(m.group(2)), f"h{len(m.group(1))}"))
            continue
        m = _BULLET.match(line)
        if m:
            paras.append((_flatten_inline(m.group(1)), "bullet"))
            continue
        if line.startswith(">"):
            paras.append((_flatten_inline(line.lstrip("> ").rstrip()), "normal"))
            continue
        paras.append((_flatten_inline(line), "normal"))

    # One insertText, then style by absolute indices. A fresh doc's body starts at
    # index 1; inserting there and styling the same ranges keeps the math simple.
    text = "".join(t + "\n" for t, _ in paras)
    if not text.strip():
        return f"https://docs.google.com/document/d/{doc_id}/edit"
    requests: list[dict] = [{"insertText": {"location": {"index": 1}, "text": text}}]

    idx = 1
    for t, kind in paras:
        start, end = idx, idx + len(t) + 1        # +1 for the newline
        if kind.startswith("h"):
            lvl = int(kind[1])
            requests.append({"updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": _NAMED[lvl]},
                "fields": "namedStyleType"}})
        elif kind == "bullet":
            requests.append({"createParagraphBullets": {
                "range": {"startIndex": start, "endIndex": end},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}})
        idx = end

    res = _gws(["docs", "documents", "batchUpdate"],
               params={"documentId": doc_id}, body={"requests": requests})
    if res.get("_error"):
        # Doc exists but formatting failed — still return the (plain) doc URL.
        pass
    return f"https://docs.google.com/document/d/{doc_id}/edit"
