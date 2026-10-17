"""The normalized listing record — the contract every adapter emits.

The CLI stays ignorant of *what* is being sold. A record is marketplace-agnostic;
domain attributes and valuation are layered on downstream (and live in the
``attributes`` / ``est_*`` / ``deal_score`` fields, null until an opt-in step runs).

Tiers (see SPEC):
  Core   — always filled by ``scrape`` (requires the per-listing detail fetch on
           OfferUp; see deals.adapters.offerup for why the cheap feed isn't enough).
  Detail — ``description`` (``--enrich`` retains the full body text).
  Vision — ``image_text`` (``--vision``, OCR of spec sheets).
  Value  — ``attributes`` / ``est_value_*`` / ``deal_score`` / ``flags`` (``--value``).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from typing import Any, Optional


# Column order for CSV export — stable, Core first, then optional tiers.
CSV_COLUMNS = [
    # Core
    "listing_id", "site", "url", "title", "price", "currency",
    "previous_price", "price_drop_amount", "price_drop_pct", "price_dropped",
    "location_name", "distance_mi", "posted_at", "condition", "is_firm",
    "seller_id", "state", "is_sold", "is_archived",
    "image_urls", "query_matched", "first_seen", "last_seen",
    # Detail
    "description",
    # Vision
    "image_text",
    # Value
    "attributes", "est_value_min", "est_value_avg", "est_value_max",
    "deal_score", "flags",
    # provenance (kept last; raw payload preserved so we never lose data)
    "raw_json",
]


@dataclass
class Listing:
    # --- Core (always) ---
    listing_id: str
    site: str
    url: str
    title: str
    price: Optional[float] = None
    currency: str = "USD"
    previous_price: Optional[float] = None     # struck-through "was" price
    price_drop_amount: Optional[float] = None   # previous_price - price
    price_drop_pct: Optional[float] = None      # 0..100
    price_dropped: bool = False
    location_name: Optional[str] = None
    distance_mi: Optional[float] = None
    posted_at: Optional[str] = None             # ISO8601 if known
    condition: Optional[str] = None
    is_firm: Optional[bool] = None
    seller_id: Optional[str] = None
    # availability (OfferUp: state enum LISTED/SOLD/UNLISTED; verified 2026-06-25).
    # A SOLD/UNLISTED listing still resolves (not null) — these let diff say WHY a
    # listing left the feed instead of lumping all departures as "gone".
    state: Optional[str] = None                 # marketplace state, upper-cased
    is_sold: Optional[bool] = None              # tracks state == SOLD
    is_archived: Optional[bool] = None
    image_urls: list = field(default_factory=list)
    query_matched: Optional[str] = None         # which sweep query surfaced it first
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

    # --- Detail (--enrich) ---
    description: Optional[str] = None

    # --- Vision (--vision) ---
    image_text: Optional[str] = None

    # --- Value (--value) ---
    attributes: dict = field(default_factory=dict)
    est_value_min: Optional[float] = None
    est_value_avg: Optional[float] = None
    est_value_max: Optional[float] = None
    deal_score: Optional[float] = None
    flags: dict = field(default_factory=dict)

    # --- provenance ---
    raw_json: Optional[str] = None

    def compute_price_drop(self) -> None:
        """Derive price_drop_* from price + previous_price. Only counts a genuine
        drop (previous_price strictly greater than price)."""
        p, pp = self.price, self.previous_price
        if p is not None and pp is not None and pp > p:
            self.price_dropped = True
            self.price_drop_amount = round(pp - p, 2)
            self.price_drop_pct = round((1 - p / pp) * 100, 1) if pp else None
        else:
            self.price_dropped = False
            self.price_drop_amount = None
            self.price_drop_pct = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def field_names(cls) -> list:
        return [f.name for f in fields(cls)]
