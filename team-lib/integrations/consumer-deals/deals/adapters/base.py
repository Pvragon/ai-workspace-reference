"""Marketplace adapter interface.

Every marketplace (OfferUp first; eBay / FB Marketplace / Craigslist / Mercari
later) implements this and emits the normalized ``Listing`` record. Downstream
consumers (catalog, filters, export, value) never know which marketplace a record
came from. Build the seam now even though only OfferUp is implemented.

Two-stage contract (forced by OfferUp's near-empty search tile — see SPEC §4):
  feed_sweep()  -> cheap listing stubs (id/title/price/location) for pre-filtering
  fill_details() -> upgrade stubs to full Core (+ description if enrich)
A ``scrape()`` convenience composes the two with optional pre-filter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterable, Optional

from ..record import Listing


class Adapter(ABC):
    #: marketplace key, e.g. "offerup"
    site: str = ""

    def __init__(self, auth: dict, lat: float, lon: float, zipcode: str = ""):
        self.auth = auth
        self.lat = lat
        self.lon = lon
        self.zipcode = zipcode

    @abstractmethod
    def feed_sweep(self, queries: Iterable[str], radius_mi: float,
                   max_pages: int = 0, progress: Optional[Callable] = None,
                   sort: Optional[str] = None) -> list:
        """Stage 1: paginate the search feed across queries, dedup by listing_id.
        Returns lightweight ``Listing`` stubs (Core fields the feed can fill).
        ``max_pages`` <= 0 means paginate to exhaustion. ``sort`` (e.g.
        ``"newest"``) requests a feed ordering when the marketplace supports it —
        used by the incremental newest-first watch poll."""
        ...

    def lookup_states(self, listing_ids: Iterable[str]) -> dict:
        """Map each listing_id to its CURRENT marketplace state string (e.g.
        ``"SOLD"`` / ``"UNLISTED"`` / ``"LISTED"``), or ``None`` when the listing
        no longer resolves (genuine deletion). Powers ``diff.reclassify_gone``.

        Default: unsupported -> empty map (callers degrade to a blanket "gone").
        Adapters whose detail endpoint exposes availability override this."""
        return {}

    @abstractmethod
    def fill_details(self, listings: list, enrich: bool = False,
                     concurrency: int = 3, progress: Optional[Callable] = None
                     ) -> list:
        """Stage 2: fetch per-listing detail to complete Core
        (previous_price, posted_at, condition, is_firm, distance, ...).
        When ``enrich`` is True, also retain ``description``. Mutates/returns
        the listings."""
        ...

    def scrape(self, queries: Iterable[str], radius_mi: float, *,
               enrich: bool = False, detail: bool = True, max_pages: int = 0,
               concurrency: int = 3, pre_filter: Optional[Callable] = None,
               progress: Optional[Callable] = None, sort: Optional[str] = None) -> list:
        """Compose feed_sweep -> (optional pre_filter) -> fill_details."""
        stubs = self.feed_sweep(queries, radius_mi, max_pages=max_pages,
                                progress=progress, sort=sort)
        if pre_filter is not None:
            stubs = [s for s in stubs if pre_filter(s)]
        if detail:
            stubs = self.fill_details(stubs, enrich=enrich,
                                      concurrency=concurrency, progress=progress)
        return stubs
