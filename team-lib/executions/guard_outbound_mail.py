#!/usr/bin/env python3
# ---
# template: execution
# version: 1.3.0
# summary: "PreToolUse guard on Bash for outbound email. DENIES a plain-text send (gws gmail +send/+reply/+forward without --html, a raw users.messages.send with no text/html part, or a drafts create/update outside gmail_update_draft.py). Otherwise ASKS the operator, through the permission prompt, before any send, and puts the recipients and the decoded body text in the prompt so he approves what he can read. --help and --dry-run pass silently, as does a +send addressed only to the operator's own addresses, read from per-user config ($MAIL_GUARD_SELF_ADDRESSES or personal/config/mail-guard.json; none configured means no exemption)."
# created: 2026-10-07
# last_updated: 2026-10-16
# maintainer: your-agent
# ---
"""guard_outbound_mail.py — no email leaves without the operator seeing the command.

Promotes two critical memories out of the memory index into a mechanism
(plan: my-lib/runtime/deliverables/261007-critical-memory-promotion-plan.md):

  feedback_outward-email-draft-for-review-before-send (2026-09-05)
      "it'll be signed as me but sent by you" is a signature instruction, not a send
      authorization. the operator: "oof. I had planned to review before you sent." Any message to
      clients or team in his voice is drafted, shown, and sent only after he says "send".
      -> every send command gets permissionDecision "ask".

  feedback_never-plain-text-email-always-html (2026-09-10)
      A plain-text email is a dead giveaway that an agent wrote it, and a plain-text Gmail
      draft flips the composer into plain-text mode (hard wraps at ~76 chars on send).
      -> plain-text sends and non-sanctioned draft writes are denied.

Deny beats ask: a plain-text send is refused outright rather than offered for approval.
Message bodies (heredocs, -m '...') are stripped before matching, so a commit message
that mentions "gws gmail +send" is not a send. Never raises; any internal error -> silent.

ClickUp / Teams posts are NOT covered here by design (the operator, 2026-10-07): they are
higher-volume and lower-stakes, so they get a lens rather than a prompt.
"""
import base64
import html
import json
import os
import re
import shlex
import sys

GWS_SHORT_SEND = re.compile(r"\bgws\s+gmail\s+\+(send|reply|reply-all|forward)\b")
GWS_RAW_SEND = re.compile(r"\bgws\s+gmail\s+users\s+(messages|drafts)\s+send\b")
GWS_DRAFT_WRITE = re.compile(r"\bgws\s+gmail\s+users\s+drafts\s+(create|update)\b")
M365_SEND = re.compile(r"\bm365\s+outlook\s+(mail|message)\s+send\b")

ASK_REASON = ("Outward message. Has the operator seen this exact text and said 'send'? Clients and "
              "team need his review first. A vendor or support send he asked for is fine to approve.")


def strip_bodies(cmd: str) -> str:
    cmd = re.sub(r"<<-?\s*'?(\w+)'?.*?^\1\s*$", " ", cmd, flags=re.DOTALL | re.M)
    cmd = re.sub(r"""-m\s+('([^']*)'|"([^"]*)")""", " -m MSG ", cmd, flags=re.DOTALL)
    return cmd


def raw_has_html(cmd: str):
    """True/False if a base64url `raw` field is visible in the command, None if not found
    (e.g. the JSON is read from a file). None is NOT treated as a pass: the send still asks."""
    m = re.search(r'"raw"\s*:\s*"([A-Za-z0-9_\-=]+)"', cmd)
    if not m:
        return None
    try:
        mime = base64.urlsafe_b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4)).decode("utf-8", "replace")
    except Exception:
        return None
    return "text/html" in mime.lower()


PREVIEW_CHARS = 1500


def _flag(tokens, *names):
    for i, t in enumerate(tokens):
        for n in names:
            if t == n and i + 1 < len(tokens):
                return tokens[i + 1]
            if t.startswith(n + "="):
                return t.split("=", 1)[1]
    return None


def _read_body(raw):
    """--body value -> text. Resolves the `$(cat FILE)` form the agent uses, so the prompt shows
    the words being sent, not a shell expression (the operator, 2026-10-14: approved a send whose body he
    never saw because the prompt showed only `--body "$(cat x.html)"`)."""
    if raw is None:
        return None
    m = re.fullmatch(r"\$\(\s*cat\s+['\"]?([^'\")]+?)['\"]?\s*\)", raw.strip())
    if m:
        try:
            with open(os.path.expanduser(m.group(1)), encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            return None
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", raw)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def describe_send(command: str) -> str:
    """Recipients + decoded body for the permission prompt. Never raises."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    parts = []
    for label, names in (("Reply to message", ("--message-id",)), ("To", ("--to",)),
                         ("Cc", ("--cc",)), ("Bcc", ("--bcc",)), ("Subject", ("--subject",))):
        v = _flag(tokens, *names)
        if v:
            parts.append(f"{label}: {v}")
    if re.search(r"\+reply\b", command) and not _flag(tokens, "--to"):
        parts.append("To: the original sender only (+reply)")
    if re.search(r"\+reply-all\b", command):
        parts.append("To: everyone on the thread (+reply-all)")
    # shlex already expanded nothing: `$(cat f)` arrives as one literal token, which _read_body resolves.
    raw_body = _flag(tokens, "--body")
    if raw_body is None:
        m = re.search(r'--body\s+"(\$\([^)]*\))"', command)
        raw_body = m.group(1) if m else None
    body = _read_body(raw_body)
    if body:
        clip = body if len(body) <= PREVIEW_CHARS else body[:PREVIEW_CHARS] + " [...]"
        parts.append("Body:\n" + clip)
    else:
        parts.append("Body: NOT VISIBLE to this guard. Deny, and ask Your Agent to paste the full text.")
    return "\n".join(parts)


def decide(command: str):
    """Return (decision, reason) or (None, None)."""
    cmd = strip_bodies(command or "")
    # Looking up syntax or previewing sends nothing; prompting on those trains reflexive approval.
    # Matched as whole shell arguments, so a body that merely mentions "--dry-run" still prompts.
    try:
        args = shlex.split(cmd, posix=True)
    except ValueError:
        args = []
    if any(t in ("--help", "-h", "--dry-run") for t in args):
        return None, None
    if "gmail_update_draft.py" in cmd:
        return None, None                      # the sanctioned multipart draft writer
    if GWS_DRAFT_WRITE.search(cmd):
        return "deny", ("BLOCKED: write Gmail drafts only via my-lib/executions/gmail_update_draft.py "
                        "(multipart/alternative). A plain-text draft flips the composer to plain-text "
                        "mode and hard-wraps at ~76 chars on send.")
    if GWS_SHORT_SEND.search(cmd) and "--html" not in cmd:
        return "deny", ("BLOCKED: every email is HTML. Add --html to this gws gmail command "
                        "(a plain-text email is a dead giveaway that an agent wrote it).")
    if GWS_RAW_SEND.search(cmd) and re.search(r"\bmessages\s+send\b", cmd) and raw_has_html(cmd) is False:
        return "deny", ("BLOCKED: this raw message has no text/html part. Every email is HTML; "
                        "build it as multipart/alternative with an HTML part.")
    if is_self_only_send(command, cmd):
        return None, None
    if GWS_SHORT_SEND.search(cmd) or GWS_RAW_SEND.search(cmd) or M365_SEND.search(cmd):
        return "ask", ASK_REASON + "\n\n" + describe_send(command)
    return None, None


# The operator's own addresses. A note-to-self is not an outward message (the operator, 2026-10-16).
#
# PER-USER CONFIGURATION, never hardcoded here. This file is shared: a hardcoded set exempted
# one person's addresses on every teammate's machine, so a teammate's agent could mail that
# person with no prompt at all. Resolution (first hit wins):
#   1. $MAIL_GUARD_SELF_ADDRESSES — comma-separated addresses
#   2. <workspace>/personal/config/mail-guard.json — {"self_addresses": ["you@example.com", ...]}
# Nothing configured -> the empty set, which means NO self-only exemption: every send asks.
# That is the safe default; an unreadable or malformed file falls back to it too.
SELF_ADDRESSES_ENV = "MAIL_GUARD_SELF_ADDRESSES"
SELF_ADDRESSES_FILE = os.path.join("personal", "config", "mail-guard.json")


def _workspace_root() -> str:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from agent_paths import workspace  # noqa: PLC0415 — one definition of the workspace root
        return str(workspace())
    except Exception:
        return os.environ.get("PVRAGON_WORKSPACE") or os.path.expanduser("~/ai-workspace")


def load_self_addresses(environ=None, workspace_root=None) -> frozenset:
    """The configured self-only addresses, lowercased. Empty when nothing is configured."""
    environ = os.environ if environ is None else environ
    raw = environ.get(SELF_ADDRESSES_ENV)
    if raw is not None:
        return frozenset(a.strip().lower() for a in raw.split(",") if a.strip())
    try:
        path = os.path.join(workspace_root or _workspace_root(), SELF_ADDRESSES_FILE)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        addrs = data.get("self_addresses") if isinstance(data, dict) else None
        if isinstance(addrs, list):
            return frozenset(str(a).strip().lower() for a in addrs if str(a).strip())
    except Exception:
        pass
    return frozenset()


def is_self_only_send(command: str, stripped: str, self_addresses=None) -> bool:
    """True only for exactly one `gws gmail +send` whose every To/Cc/Bcc address is the operator's own.
    Replies and forwards never qualify: their recipients come from the thread, not the command line.
    Any second send in the same command, any raw/m365 send, or any unparseable recipient -> False."""
    sends = list(GWS_SHORT_SEND.finditer(stripped))
    if len(sends) != 1 or sends[0].group(1) != "send" or GWS_RAW_SEND.search(stripped) or M365_SEND.search(stripped):
        return False
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False
    recips = []
    for i, t in enumerate(tokens):
        for flag in ("--to", "--cc", "--bcc"):
            if t == flag and i + 1 < len(tokens):
                recips.append(tokens[i + 1])
            elif t.startswith(flag + "="):
                recips.append(t.split("=", 1)[1])
    addrs = [a.strip().lower() for r in recips for a in r.split(",") if a.strip()]
    addrs = [re.sub(r"^.*<([^>]+)>$", r"\1", a) for a in addrs]  # "Name <addr>" -> addr
    mine = load_self_addresses() if self_addresses is None else self_addresses
    return bool(addrs) and bool(mine) and all(a in mine for a in addrs)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        decision, reason = decide((payload.get("tool_input") or {}).get("command", ""))
    except Exception:
        return 0
    if decision:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": decision,
            "permissionDecisionReason": reason}}))
    return 0


def run(command: str):
    return decide(command)


if __name__ == "__main__":
    sys.exit(main())
