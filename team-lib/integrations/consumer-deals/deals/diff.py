"""Catalog diff — the detection primitive under deal-watching.

Compare an OLD catalog to a NEW one, keyed by ``listing_id``, and classify every
listing as new / gone / price-dropped / price-raised / unchanged. Domain-agnostic:
pure delta on the normalized record, no valuation needed.

Honesty note: ``gone`` means "no longer in the new catalog" — it could be sold,
delisted, expired, paused, or simply outside the radius/age window this run.

We CAN often do better than a blanket "gone": OfferUp's verified ``state`` enum
(LISTED/SOLD/UNLISTED; 2026-06-25) lets us split departures into ``sold`` (a
real LISTED->SOLD transition) and ``unlisted`` (seller pulled it, NOT sold),
reserving ``gone`` for genuine disappearance (``listing: null``). When the
new-side record already carries a SOLD/UNLISTED state, ``diff_catalogs`` splits
it directly; otherwise ``reclassify_gone`` re-queries the departed ids' current
state (a cheap, gone-ids-only pass) and reclassifies. We still NEVER claim "sold"
without the state field saying so.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .record import Listing

NEW = "new"
GONE = "gone"
SOLD = "sold"
UNLISTED = "unlisted"
PRICE_DROP = "price_drop"
PRICE_RISE = "price_rise"
UNCHANGED = "unchanged"
UNKNOWN = "unknown"          # id in both but a price is missing -> can't compute delta

# verified OfferUp state values (reference_offerup-sold-state-fields)
_SOLD_STATES = {"SOLD"}
_UNLISTED_STATES = {"UNLISTED"}


def _state(L: Listing) -> str:
    return (L.state or "").upper()


def is_sold_state(L: Listing) -> bool:
    return L.is_sold is True or _state(L) in _SOLD_STATES


def is_unlisted_state(L: Listing) -> bool:
    return _state(L) in _UNLISTED_STATES


@dataclass
class PriceChange:
    listing: Listing          # new-side record
    prev_price: float
    new_price: float

    @property
    def delta(self) -> float:
        return round(self.new_price - self.prev_price, 2)

    @property
    def pct(self) -> Optional[float]:
        if not self.prev_price:
            return None
        return round((self.new_price - self.prev_price) / self.prev_price * 100, 1)


@dataclass
class DiffResult:
    new: list = field(default_factory=list)          # Listing
    gone: list = field(default_factory=list)         # Listing (old-side): truly absent
    sold: list = field(default_factory=list)         # Listing: LISTED -> SOLD
    unlisted: list = field(default_factory=list)     # Listing: LISTED -> UNLISTED (not sold)
    price_drop: list = field(default_factory=list)   # PriceChange
    price_rise: list = field(default_factory=list)   # PriceChange
    unchanged: list = field(default_factory=list)    # Listing
    unknown: list = field(default_factory=list)      # Listing

    @property
    def counts(self) -> dict:
        return {
            "new": len(self.new), "gone": len(self.gone),
            "sold": len(self.sold), "unlisted": len(self.unlisted),
            "price_drop": len(self.price_drop), "price_rise": len(self.price_rise),
            "unchanged": len(self.unchanged), "unknown": len(self.unknown),
        }

    def has_changes(self) -> bool:
        return bool(self.new or self.price_drop)


def diff_catalogs(old: list, new: list) -> DiffResult:
    o = {L.listing_id: L for L in old}
    n = {L.listing_id: L for L in new}
    r = DiffResult()
    for lid, L in n.items():
        prev = o.get(lid)
        if prev is None:
            r.new.append(L)
            continue
        # An in-place LISTED->SOLD/UNLISTED transition (the new-side record carries
        # the state) takes priority over any price delta — the deal's availability
        # changed, which is what a watcher cares about.
        if is_sold_state(L) and not is_sold_state(prev):
            r.sold.append(L)
            continue
        if is_unlisted_state(L) and not is_unlisted_state(prev):
            r.unlisted.append(L)
            continue
        op, np_ = prev.price, L.price
        if op is None or np_ is None:
            (r.unchanged if op == np_ else r.unknown).append(L)
        elif np_ < op:
            r.price_drop.append(PriceChange(L, op, np_))
        elif np_ > op:
            r.price_rise.append(PriceChange(L, op, np_))
        else:
            r.unchanged.append(L)
    for lid, L in o.items():
        if lid not in n:
            r.gone.append(L)
    return r


def reclassify_gone(result: DiffResult,
                    state_lookup: Callable[[str], Optional[str]]) -> DiffResult:
    """Split the ``gone`` bucket into sold / unlisted / (truly) gone by re-querying
    each departed listing's CURRENT state.

    ``state_lookup(listing_id)`` returns the live state string (e.g. ``"SOLD"``,
    ``"UNLISTED"``, ``"LISTED"``) or ``None`` when the listing no longer resolves
    (``listing: null`` — genuine deletion). The departed record is stamped with
    the looked-up state so downstream output/CSV reflect reality. Mutates and
    returns ``result``. Cheap: only the gone ids are queried, not the census."""
    still_gone = []
    for L in result.gone:
        st = state_lookup(L.listing_id)
        if st is None:
            still_gone.append(L)                  # null/removed -> honestly "gone"
            continue
        L.state = st.upper()
        if is_sold_state(L):
            L.is_sold = True
            result.sold.append(L)
        elif is_unlisted_state(L):
            result.unlisted.append(L)
        else:
            still_gone.append(L)                  # back in LISTED, or unknown state
    result.gone = still_gone
    return result


# ---- machine-readable delta CSV ----
DIFF_COLUMNS = [
    "change", "listing_id", "site", "url", "title", "price", "prev_price",
    "price_delta", "price_change_pct", "state", "distance_mi", "posted_at",
    "seller_id",
]


def _row(change: str, L: Listing, prev: Optional[float] = None,
         delta: Optional[float] = None, pct: Optional[float] = None) -> dict:
    def s(v):
        return "" if v is None else v
    return {
        "change": change, "listing_id": L.listing_id, "site": L.site, "url": L.url,
        "title": L.title, "price": s(L.price), "prev_price": s(prev),
        "price_delta": s(delta), "price_change_pct": s(pct), "state": s(L.state),
        "distance_mi": s(L.distance_mi), "posted_at": s(L.posted_at),
        "seller_id": s(L.seller_id),
    }


def write_diff(result: DiffResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    rows += [_row(NEW, L) for L in result.new]
    rows += [_row(PRICE_DROP, pc.listing, pc.prev_price, pc.delta, pc.pct)
             for pc in result.price_drop]
    rows += [_row(PRICE_RISE, pc.listing, pc.prev_price, pc.delta, pc.pct)
             for pc in result.price_rise]
    rows += [_row(SOLD, L) for L in result.sold]
    rows += [_row(UNLISTED, L) for L in result.unlisted]
    rows += [_row(GONE, L) for L in result.gone]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=DIFF_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path
