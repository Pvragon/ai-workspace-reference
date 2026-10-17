"""Alert sinks for ``deals watch``.

The watcher's job ends at "tell the human, fast" — it NEVER contacts sellers or
places offers (SPEC hard boundary). A poll produces a list of actionable changes
(new listings, price drops, and — on a full re-scan — sold/unlisted departures);
this module formats them and ships them to a sink.

Sinks are pluggable; ``email`` (via the workspace ``gws gmail +send`` helper) is
the one wired today. Every sink degrades soft: a delivery failure is warned, not
fatal, and the formatted alert is always available on stdout so nothing is lost.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from .diff import DiffResult


def _fmt_listing(L) -> str:
    price = f"${L.price:.0f}" if L.price is not None else "$—"
    mi = f"{L.distance_mi:.0f}mi" if L.distance_mi is not None else ""
    score = ""
    if getattr(L, "deal_score", None) is not None:
        score = f"  score {L.deal_score:.0f}"
    val = ""
    if getattr(L, "est_value_avg", None) is not None:
        val = f"  ~${L.est_value_avg:.0f} value"
    head = f"  {price:>7} {mi:>5}{score}{val}  {L.title[:60]}"
    return f"{head}\n     {L.url}"


def format_alert(result: DiffResult, query: str, *, drops=None,
                 location: str = "", incremental: bool = False) -> tuple:
    """Return ``(subject, body)`` for the actionable changes. ``drops`` lets the
    caller pass an already-filtered price-drop list (e.g. ``--min-drop``)."""
    drops = result.price_drop if drops is None else drops
    c = result.counts
    mode = "new listings" if incremental else "full re-scan"
    n_act = len(result.new) + len(drops) + len(result.sold)
    loc = f" near {location}" if location else ""
    subject = (f"[deals] {len(result.new)} new, {len(drops)} price drops "
               f"for “{query}”{loc}")

    lines = [f"Deal watch — “{query}”{loc}  ({mode})", ""]
    if result.new:
        lines.append(f"NEW ({len(result.new)}):")
        for L in sorted(result.new, key=lambda L: (L.price is None, L.price or 0)):
            lines.append(_fmt_listing(L))
        lines.append("")
    if drops:
        lines.append(f"PRICE DROPS ({len(drops)}):")
        for pc in sorted(drops, key=lambda pc: (pc.pct if pc.pct is not None else 0)):
            L = pc.listing
            tag = f"${pc.prev_price:.0f}->${pc.new_price:.0f} ({pc.pct:+.0f}%)"
            lines.append(f"  {tag:>22}  {L.title[:55]}\n     {L.url}")
        lines.append("")
    if result.sold:                       # informational (full re-scan only)
        lines.append(f"SOLD since last run ({len(result.sold)}) — these are gone:")
        for L in result.sold:
            lines.append(f"  {L.title[:60]}")
        lines.append("")
    if n_act == 0:
        lines.append("No new listings or price drops this run.")
    lines.append("")
    lines.append("— deals watch (read-only; verify any too-good deal in person, "
                 "cash, public safe-exchange).")
    return subject, "\n".join(lines)


def send_email(subject: str, body: str, to: str) -> bool:
    """Send via the workspace ``gws gmail +send`` helper. Returns True on success.
    Fails soft (warns) when gws is absent or the send errors."""
    if not shutil.which("gws"):
        print("  notify: gws CLI not found on PATH — email NOT sent "
              "(alert is above).")
        return False
    try:
        r = subprocess.run(
            ["gws", "gmail", "+send", "--to", to, "--subject", subject,
             "--body", body],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  notify: email send failed ({e}).")
        return False
    if r.returncode != 0:
        print(f"  notify: email send failed: {r.stderr.strip()[:200]}")
        return False
    print(f"  notify: emailed {to}")
    return True


def dispatch(result: DiffResult, query: str, *, sink: str = "none",
             email_to: Optional[str] = None, drops=None, location: str = "",
             incremental: bool = False) -> dict:
    """Format the alert (always printed) and route to the chosen sink.
    Returns ``{"subject","sent"}``."""
    subject, body = format_alert(result, query, drops=drops, location=location,
                                 incremental=incremental)
    print("\n" + body)
    sent = False
    if sink == "email":
        if not email_to:
            print("  notify: --notify email needs --email-to ADDR — not sent.")
        else:
            sent = send_email(subject, body, email_to)
    return {"subject": subject, "sent": sent}
