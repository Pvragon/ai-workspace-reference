"""OfferUp adapter parsing — mock the GraphQL transport, verify stub + detail
mapping and the two-stage compose. No network."""
from deals.adapters.offerup import OfferUpAdapter


AUTH = {"x-ou-d-token": "web-deadbeef", "ou-session-id": "web-deadbeef@1",
        "user-agent": "ua"}


def _adapter():
    return OfferUpAdapter(AUTH, 32.7997, -117.0917, "92124")


def _feed_page(listings, cursor):
    return {"data": {"modularFeed": {
        "looseTiles": [{"__typename": "ModularFeedTileListing", "listing": L} for L in listings],
        "modules": [], "pageCursor": cursor}}}


def test_feed_sweep_paginates_and_dedups(monkeypatch):
    a = _adapter()
    pages = [
        _feed_page([{"listingId": "1", "title": "PC A", "price": "300",
                     "formattedPrice": "$300", "locationName": "San Diego, CA",
                     "flags": ["LOCAL_PICKUP"]},
                    {"listingId": "2", "title": "PC B", "price": "450",
                     "formattedPrice": "$450", "locationName": "El Cajon, CA",
                     "flags": []}], "cursorA"),
        _feed_page([{"listingId": "2", "title": "PC B", "price": "450",
                     "formattedPrice": "$450", "locationName": "El Cajon, CA",
                     "flags": []},  # dup
                    {"listingId": "3", "title": "PC C", "price": "600",
                     "formattedPrice": "$600", "locationName": "Carlsbad, CA",
                     "flags": []}], "cursorB"),
        _feed_page([], ""),  # empty -> stop
    ]
    calls = {"i": 0}

    def fake_post(op, query, variables, tries=3):
        i = calls["i"]; calls["i"] += 1
        return pages[i] if i < len(pages) else _feed_page([], "")

    monkeypatch.setattr(a, "_post", fake_post)
    stubs = a.feed_sweep(["gaming pc"], radius_mi=40, max_pages=0)
    ids = sorted(s.listing_id for s in stubs)
    assert ids == ["1", "2", "3"]
    s1 = next(s for s in stubs if s.listing_id == "1")
    assert s1.price == 300.0
    assert s1.url == "https://offerup.com/item/detail/1"
    assert s1.location_name == "San Diego, CA"
    assert s1.query_matched == "gaming pc"


def test_fill_details_maps_core_and_drop(monkeypatch):
    a = _adapter()
    stubs = a.feed_sweep.__self__  # noqa
    from deals.record import Listing
    L = Listing(listing_id="1", site="offerup", url="u", title="PC", price=300.0,
                raw_json='{"tile": {}}')

    detail = {"data": {"listing": {
        "listingId": "1", "title": "Gaming PC RTX 2070", "price": "300",
        "originalPrice": "380", "priceDropPercentage": "21%",
        "formattedPrice": "$300", "conditionText": "Used",
        "isFirmOnPrice": False, "postDate": "2026-06-20T10:00:00Z",
        "description": "Great rig, price is firm", "ownerId": "56721479",
        "state": "listed", "isSold": False, "isArchived": False,
        "distance": {"value": 12.34, "unit": "MILE"},
        "photos": [{"detail": {"url": "https://images.offerup.com/a.jpg"}},
                   {"detail": {"url": "https://images.offerup.com/b.jpg"}},
                   {"thumbnail": {"url": "https://images.offerup.com/c.jpg"}}]}}}

    monkeypatch.setattr(a, "_post", lambda *args, **kw: detail)
    out = a.fill_details([L], enrich=True, concurrency=1)
    r = out[0]
    assert r.previous_price == 380.0
    assert r.price_dropped is True
    assert r.price_drop_amount == 80.0
    assert r.condition == "Used"
    assert r.is_firm is False
    assert r.distance_mi == 12.3
    assert r.posted_at == "2026-06-20T10:00:00Z"
    assert r.description == "Great rig, price is firm"
    assert r.seller_id == "56721479"
    assert r.state == "LISTED"      # upper-cased on capture
    assert r.is_sold is False and r.is_archived is False
    assert r.image_urls == ["https://images.offerup.com/a.jpg",
                            "https://images.offerup.com/b.jpg"]  # only .detail.url
    assert r.flags.get("firm") is True   # flags wired into the pipeline


def test_previous_price_cleared_when_no_drop(monkeypatch):
    a = _adapter()
    from deals.record import Listing
    L = Listing(listing_id="1", site="offerup", url="u", title="PC", price=300.0,
                raw_json='{"tile": {}}')
    # originalPrice == price -> not a real "was" price, should not populate
    detail = {"data": {"listing": {"listingId": "1", "title": "PC", "price": "300",
              "originalPrice": "300", "distance": {"value": 5.0, "unit": "MILE"}}}}
    monkeypatch.setattr(a, "_post", lambda *args, **kw: detail)
    r = a.fill_details([L], concurrency=1)[0]
    assert r.previous_price is None
    assert r.price_dropped is False


def test_enrich_off_drops_description(monkeypatch):
    a = _adapter()
    from deals.record import Listing
    L = Listing(listing_id="1", site="offerup", url="u", title="PC",
                raw_json='{"tile": {}}')
    detail = {"data": {"listing": {"listingId": "1", "title": "PC", "price": "300",
              "originalPrice": "300", "description": "spec text",
              "distance": {"value": 5.0, "unit": "MILE"}}}}
    monkeypatch.setattr(a, "_post", lambda *args, **kw: detail)
    out = a.fill_details([L], enrich=False, concurrency=1)
    assert out[0].description is None
    assert out[0].distance_mi == 5.0
