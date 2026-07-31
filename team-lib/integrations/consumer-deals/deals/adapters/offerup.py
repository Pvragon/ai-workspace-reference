"""OfferUp adapter — adapter #1.

Talks to OfferUp's internal Apollo GraphQL endpoint. All field names / query
signatures verified live 2026-06-22 (see deals-cli FINDINGS / memory
reference_offerup-scraping-graphql).

Why two stages: the search **tile** only usefully fills
``listing_id/title/price/location/flags`` — condition, is_firm, posted date and
the price-drop fields are ALL detail-only, and the tile has no date field at all.
So a real Core record requires the per-listing detail fetch (cheap: ~2,600
details concurrently in a few minutes, 0 errors observed).

Auth: the device token is not validated; we mint one locally (deals.auth) and
self-heal by re-minting on the rare failure. Distance is localized by sending an
unsigned ``userdata`` JWT built from the user's lat/lon (deals.geo).
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
import urllib.error
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from .base import Adapter
from ..record import Listing
from ..geo import build_userdata_jwt
from ..flags import compute_flags
from ..throttle import RateLimiter, CircuitBreaker, ThrottledError, backoff_delay
from .. import auth as auth_mod
from .. import cache as cache_mod

ENDPOINT = "https://offerup.com/api/graphql"
EXPERIMENT = "experimentmodel24"

_FEED_QUERY = (
    "query GetModularFeed($params: [SearchParam]) {"
    " modularFeed(params: $params) {"
    " looseTiles { __typename ... on ModularFeedTileListing {"
    " listing { listingId title price formattedPrice locationName flags } } }"
    " modules { __typename ... on ModularFeedModuleGrid { grid { tiles {"
    " __typename ... on ModularFeedTileListing {"
    " listing { listingId title price formattedPrice locationName flags } } } } } }"
    " pageCursor } }"
)

_DETAIL_QUERY = (
    "query GetListing($id: ID!) { listing(listingId: $id) {"
    " listingId title price originalPrice priceDropPercentage formattedPrice"
    " conditionText isFirmOnPrice postDate description ownerId"
    " state isSold isArchived"
    " distance { value unit } photos { detail { url } } } }"
)

# minimal availability re-query for departed listings (reclassify_gone)
_STATE_QUERY = "query GetListing($id: ID!) { listing(listingId: $id) { listingId state } }"

ITEM_URL = "https://offerup.com/item/detail/{}"

# A run of this many consecutive empty detail responses (HTTP 200 + listing:null)
# is the signature of a soft block (vs. a one-off gone listing) — back off.
NULL_BLOCK_THRESHOLD = 12


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _to_float(v) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


class OfferUpAdapter(Adapter):
    site = "offerup"

    def __init__(self, auth: dict, lat: float, lon: float, zipcode: str = "", *,
                 rps: float = 3.0, cache: bool = True,
                 cache_ttl: float = cache_mod.DEFAULT_TTL_S, refresh: bool = False):
        super().__init__(auth, lat, lon, zipcode)
        self._userdata = build_userdata_jwt(lat, lon, zipcode)
        # resilience: trickle requests, trip fast on throttling, reuse cached detail
        self._limiter = RateLimiter(rps=rps)
        self._breaker = CircuitBreaker(threshold=8)
        self._cache = cache
        self._cache_ttl = cache_ttl
        self._refresh = refresh
        self.last_throttled = False        # set when a detail pass backs off early

    # ---- transport ----
    def _headers(self, op: str) -> dict:
        a = self.auth
        return {
            "content-type": "application/json",
            "x-ou-operation-name": op,
            "x-ou-d-token": a["x-ou-d-token"],
            "ou-session-id": a["ou-session-id"],
            "ou-experiment-data": json.dumps({"datamodel_id": EXPERIMENT}),
            "userdata": self._userdata,
            "user-agent": a.get("user-agent", auth_mod.DEFAULT_UA),
        }

    def _post(self, op: str, query: str, variables: dict, tries: int = 3) -> Optional[dict]:
        """Rate-limited, breaker-guarded POST. Raises ThrottledError when the
        endpoint is clearly throttling us (so the run backs off instead of
        hammering). Returns parsed JSON, or None on non-throttle failure."""
        self._breaker.check()                      # fail fast if already tripped
        body = json.dumps({"operationName": op, "variables": variables,
                           "query": query}).encode()
        for attempt in range(tries):
            self._limiter.acquire()                # trickle, don't burst
            try:
                req = urllib.request.Request(ENDPOINT, data=body,
                                             headers=self._headers(op), method="POST")
                with urllib.request.urlopen(req, timeout=30) as r:
                    self._breaker.record_success()
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):           # self-heal: re-mint token
                    self.auth = auth_mod.refresh(self.site)
                if e.code in (403, 429, 503):      # throttle signals
                    if self._breaker.record_throttle():
                        self._breaker.check()       # -> ThrottledError
                    time.sleep(backoff_delay(attempt))
                    continue
                time.sleep(backoff_delay(attempt))
            except Exception:                      # noqa: BLE001  (network hiccup)
                time.sleep(backoff_delay(attempt))
        return None

    # ---- search params ----
    @staticmethod
    def _search_params(q: str, zipcode: str, radius_mi: float, cursor: str,
                       sort: Optional[str] = None) -> list:
        p = [
            {"key": "q", "value": q},
            {"key": "platform", "value": "web"},
            {"key": "zipcode", "value": str(zipcode)},
            {"key": "radius", "value": str(int(radius_mi))},
            {"key": "experiment_id", "value": EXPERIMENT},
            {"key": "page_cursor", "value": cursor},
            {"key": "limit", "value": "50"},
            {"key": "searchSessionId", "value": str(uuid.uuid4())},
        ]
        # sort=newest is honored but is recency-WEIGHTED, not strict postDate-desc
        # (verified 2026-06-25) — callers must bound pages, not trust stop-on-seen.
        if sort:
            p.append({"key": "sort", "value": sort})
        return p

    @staticmethod
    def _iter_tile_listings(feed: dict):
        for t in feed.get("looseTiles") or []:
            if t.get("listing"):
                yield t["listing"]
        for m in feed.get("modules") or []:
            grid = m.get("grid") or {}
            for t in grid.get("tiles") or []:
                if t.get("listing"):
                    yield t["listing"]

    def _stub(self, L: dict, query: str) -> Listing:
        now = _now_iso()
        return Listing(
            listing_id=L["listingId"],
            site=self.site,
            url=ITEM_URL.format(L["listingId"]),
            title=L.get("title") or "",
            price=_to_float(L.get("price")),
            currency="USD",
            location_name=L.get("locationName"),
            is_firm=None,
            query_matched=query,
            first_seen=now,
            last_seen=now,
            raw_json=json.dumps({"tile": L}),
        )

    # ---- stage 1 ----
    def feed_sweep(self, queries: Iterable[str], radius_mi: float,
                   max_pages: int = 0, progress: Optional[Callable] = None,
                   sort: Optional[str] = None) -> list:
        by_id: dict = {}
        for q in queries:
            cursor, prev, pages = "", None, 0
            while True:
                d = self._post("GetModularFeed", _FEED_QUERY,
                               {"params": self._search_params(q, self.zipcode, radius_mi,
                                                              cursor, sort)})
                feed = ((d or {}).get("data") or {}).get("modularFeed") or {}
                got = 0
                for L in self._iter_tile_listings(feed):
                    got += 1
                    lid = L["listingId"]
                    if lid not in by_id:
                        by_id[lid] = self._stub(L, q)
                cursor = feed.get("pageCursor") or ""
                pages += 1
                if progress:
                    progress("feed", q, pages, len(by_id))
                if got == 0 or not cursor or cursor == prev:
                    break
                if max_pages and pages >= max_pages:
                    break
                prev = cursor
        return list(by_id.values())

    # ---- stage 2 ----
    def _apply_detail(self, L: Listing, det: dict, enrich: bool) -> Listing:
        L.title = det.get("title") or L.title
        if _to_float(det.get("price")) is not None:
            L.price = _to_float(det.get("price"))
        # originalPrice is ALWAYS present (equals price when there's no drop) —
        # only record previous_price when it genuinely differs, so the column is
        # a real "was" price (up or down), not noise on every row.
        op = _to_float(det.get("originalPrice"))
        L.previous_price = op if (op is not None and L.price is not None and op != L.price) else None
        L.condition = det.get("conditionText")
        L.is_firm = det.get("isFirmOnPrice")
        L.posted_at = det.get("postDate")
        L.seller_id = det.get("ownerId")
        # availability — verified fields: state (enum), isSold, isArchived.
        st = det.get("state")
        L.state = st.upper() if isinstance(st, str) else st
        L.is_sold = det.get("isSold")
        L.is_archived = det.get("isArchived")
        dist = det.get("distance") or {}
        if dist.get("value") is not None:
            L.distance_mi = round(float(dist["value"]), 1)
        photos = det.get("photos") or []
        L.image_urls = [p["detail"]["url"] for p in photos
                        if isinstance(p, dict) and (p.get("detail") or {}).get("url")]
        if enrich:
            L.description = det.get("description") or ""
        L.compute_price_drop()
        L.flags = compute_flags(L)        # domain-agnostic guardrail signals
        L.last_seen = _now_iso()
        # preserve raw detail alongside the tile
        try:
            raw = json.loads(L.raw_json) if L.raw_json else {}
        except (TypeError, json.JSONDecodeError):
            raw = {}
        raw["detail"] = det
        L.raw_json = json.dumps(raw)
        return L

    def fill_details(self, listings: list, enrich: bool = False,
                     concurrency: int = 3, progress: Optional[Callable] = None) -> list:
        """Fill Core from per-listing detail. Cache-first (free re-runs / resume),
        rate-limited, and throttle-aware: on a detected block it stops early and
        returns partial results (already cached) rather than hammering. Check
        ``self.last_throttled`` after the call."""
        self.last_throttled = False
        site = self.site

        # 1) serve from cache where possible — zero API calls
        to_fetch, cached_n = [], 0
        for L in listings:
            if self._cache and not self._refresh:
                det = cache_mod.get(site, L.listing_id, ttl=self._cache_ttl)
                if det is not None:
                    self._apply_detail(L, det, enrich)
                    cached_n += 1
                    continue
            to_fetch.append(L)
        if progress:
            progress("cache", None, cached_n, len(to_fetch))
        if not to_fetch:
            return listings

        # 2) fetch the misses, trickled + breaker-guarded
        lock = threading.Lock()
        state = {"consec_null": 0, "throttled": False}

        def fetch(L: Listing):
            d = self._post("GetListing", _DETAIL_QUERY, {"id": L.listing_id})
            return L, ((d or {}).get("data") or {}).get("listing")

        done, ok = 0, 0
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
            futs = {ex.submit(fetch, L): L for L in to_fetch}
            for f in as_completed(futs):
                try:
                    L, det = f.result()
                except ThrottledError:
                    state["throttled"] = True
                    break
                done += 1
                if det:
                    self._apply_detail(L, det, enrich)
                    if self._cache:
                        cache_mod.set(site, L.listing_id, det)
                    ok += 1
                    with lock:
                        state["consec_null"] = 0
                else:
                    with lock:
                        state["consec_null"] += 1
                        if state["consec_null"] >= NULL_BLOCK_THRESHOLD:
                            state["throttled"] = True
                if progress and done % 50 == 0:
                    progress("detail", None, done, ok)
                if state["throttled"]:
                    break
            for fut in futs:                      # best-effort stop of queued work
                fut.cancel()

        self.last_throttled = state["throttled"]
        if progress:
            progress("detail", None, done, ok)
        return listings


    # ---- availability re-query (powers diff.reclassify_gone) ----
    def lookup_states(self, listing_ids) -> dict:
        """Current state for each id: ``"SOLD"``/``"UNLISTED"``/``"LISTED"`` or
        ``None`` if the listing no longer resolves. Trickled + breaker-guarded;
        on a detected block it returns what it has so far (partial)."""
        out: dict = {}
        for lid in listing_ids:
            try:
                d = self._post("GetListing", _STATE_QUERY, {"id": lid})
            except ThrottledError:
                self.last_throttled = True
                break
            L = ((d or {}).get("data") or {}).get("listing")
            if L is None:
                out[lid] = None                 # genuine deletion (listing: null)
            else:
                st = L.get("state")
                out[lid] = st.upper() if isinstance(st, str) else st
        return out


def default_queries(base: str) -> list:
    """Expand one user query into a small sweep that catches differently-titled
    listings (deduped downstream by listing_id). Conservative; the user query is
    always first/primary."""
    base = base.strip()
    return [base]
