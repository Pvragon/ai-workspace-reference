"""Email delivery via the gws CLI (same path as executions/pr_status_digest.py)."""
from __future__ import annotations

import subprocess


def send_email(recipient: str, subject: str, body: str, html: bool = False) -> tuple[bool, str]:
    """Send via `gws gmail +send`. Set html=True to send an HTML body."""
    cmd = ["gws", "gmail", "+send",
           "--to", recipient,
           "--subject", subject,
           "--body", body]
    if html:
        cmd.append("--html")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return False, "gws not on PATH"
    except subprocess.TimeoutExpired:
        return False, "gws send timed out"
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "unknown error").strip()
    return True, "sent"
