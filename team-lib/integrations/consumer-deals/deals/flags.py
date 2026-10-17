"""Generic, domain-agnostic guardrail flags (hard-won from the PoC).

Baked into the generic layer so every future hunt inherits them. These are
*signals to annotate, never verdicts that drop*. Nothing here removes a listing —
a flag adds context the downstream valuation/ranking layer can weight. In
particular a too-good-to-be-true price is a VERIFY-HARD signal, not a "scam"
drop: desperate/clueless sellers posting genuine steals are exactly the target
(see memory feedback_deal-mining-scam-flag-is-verify-not-verdict). So this module
never emits an exclusionary flag and the pipeline never drops on flags.

  dealer       — financing/teaser-price storefront ("no credit needed", "$X down",
                 "$X/week", "financing available") whose sticker price is not the
                 real cash price. Narrow on purpose: an individual mentioning
                 "financial reasons" is NOT a dealer.
  firm         — seller flagged the price as firm (from is_firm) or says so in text.
  broken       — "has issues / needs repair / for parts / not working".
  stale        — listing age beyond a freshness threshold (caller passes age days).
"""
from __future__ import annotations

import re
from typing import Optional

from .record import Listing

_DEALER = re.compile(
    r"(\bno credit( needed| check)?\b|\bfinancing\b|\$\d[\d,]*\s*(down|/\s*(week|wk|mo|month))"
    r"|\bas low as\b|\bpayments?\s+(starting|as low)\b|\blease(-| )?to(-| )?own\b|"
    r"\bbuy here pay here\b|\b0%? *apr\b|\bweekly payments?\b)", re.I)
_BROKEN = re.compile(
    r"\b(for parts|parts only|not working|doesn'?t (work|turn on|boot|post)|"
    r"won'?t (work|turn on|boot|post)|needs? (repair|fixing|diagnostic|work)|"
    r"has (some )?(issues|problems)|broken|cracked|damaged|as[- ]is|read description)\b",
    re.I)
_FIRM_TEXT = re.compile(r"\b(price is firm|firm on price|firm price|no low ?ball\w*|no offers?)\b", re.I)


def compute_flags(listing: Listing, stale_days: Optional[int] = None,
                  age_days: Optional[float] = None) -> dict:
    """Return a flags dict for a listing. Looks at title + description.
    ``age_days`` (if known) + ``stale_days`` threshold drive the stale flag."""
    text = " ".join(filter(None, [listing.title, listing.description])).strip()
    flags: dict = {}
    if _DEALER.search(text):
        flags["dealer"] = True
    if _BROKEN.search(text):
        flags["broken"] = True
    if bool(listing.is_firm) or _FIRM_TEXT.search(text):
        flags["firm"] = True
    if stale_days is not None and age_days is not None and age_days > stale_days:
        flags["stale"] = True
    return flags
