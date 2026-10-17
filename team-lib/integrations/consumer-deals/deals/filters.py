"""Post-filters: radius + listing age. Config-defaulted, CLI-overridable.

Radius: OfferUp's ``radius`` param is NOT enforced on deep pagination (the feed
is distance-RANKED, not limited) -> always post-filter on the per-listing
``distance_mi`` we derive from the localized detail distance.

Age: post-filter on ``posted_at`` (detail-only on OfferUp). Default lives in
config, e.g. "2mo".
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from .record import Listing

_AGE_RE = re.compile(r"^\s*(\d+)\s*(d|w|mo|m|y)\s*$", re.I)
# d=days w=weeks mo=months(30d) m=months(30d) y=years(365d)
_UNIT_DAYS = {"d": 1, "w": 7, "mo": 30, "m": 30, "y": 365}


def parse_age(spec: str) -> timedelta:
    """'2mo' -> 60 days, '30d' -> 30 days, '6w' -> 42 days, '1y' -> 365 days."""
    m = _AGE_RE.match(spec or "")
    if not m:
        raise ValueError(f"bad age spec {spec!r} (use e.g. 30d, 6w, 2mo, 1y)")
    n, unit = int(m.group(1)), m.group(2).lower()
    return timedelta(days=n * _UNIT_DAYS[unit])


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    txt = s.strip()
    # epoch millis or seconds
    if txt.isdigit():
        v = int(txt)
        if v > 10_000_000_000:  # ms
            v //= 1000
        return datetime.fromtimestamp(v, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def within_radius(listing: Listing, radius_mi: float) -> bool:
    d = listing.distance_mi
    # keep listings whose distance is unknown only if no radius constraint matters;
    # here unknown distance => exclude (we can't prove it's in range).
    return d is not None and d <= radius_mi + 1e-9


def within_age(listing: Listing, max_age: timedelta, now: Optional[datetime] = None) -> bool:
    dt = _parse_dt(listing.posted_at)
    if dt is None:
        return True  # unknown posted_at: don't drop on age alone
    now = now or datetime.now(tz=timezone.utc)
    return (now - dt) <= max_age


def apply(listings: list, radius_mi: Optional[float], max_age: Optional[str],
          now: Optional[datetime] = None) -> tuple:
    """Return (kept, dropped_counts). radius_mi/max_age None => that filter off."""
    age_td = parse_age(max_age) if max_age else None
    kept = []
    dropped = {"radius": 0, "age": 0}
    for L in listings:
        if radius_mi is not None and not within_radius(L, radius_mi):
            dropped["radius"] += 1
            continue
        if age_td is not None and not within_age(L, age_td, now=now):
            dropped["age"] += 1
            continue
        kept.append(L)
    return kept, dropped
