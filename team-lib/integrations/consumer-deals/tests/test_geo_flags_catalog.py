"""Geo (userdata JWT + haversine), guardrail flags, and CSV round-trip."""
import base64
import json

from deals import geo, catalog
from deals.record import Listing
from deals.flags import compute_flags


# ---- geo ----
def test_userdata_jwt_decodes_to_location():
    jwt = geo.build_userdata_jwt(32.7997, -117.0917, "92124")
    assert jwt.count(".") == 2 and jwt.endswith(".")
    header_b64, payload_b64, sig = jwt.split(".")
    assert sig == ""

    def dec(seg):
        return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))

    assert dec(header_b64) == {"alg": "none"}
    loc = dec(payload_b64)["location"]
    assert loc["zipCode"] == "92124"
    assert loc["latitude"] == 32.7997
    assert loc["longitude"] == -117.0917


def test_haversine_known_distance():
    sd = (32.7157, -117.1611)
    carlsbad = (33.1581, -117.3506)
    d = geo.haversine_mi(sd, carlsbad)
    assert 25 < d < 40  # ~31 mi


# ---- flags ----
def test_flag_dealer():
    L = Listing(listing_id="x", site="s", url="u", title="RTX 5070 Ti $680",
                description="No credit needed! $10 down, $40/week")
    f = compute_flags(L)
    assert f.get("dealer") is True


def test_flag_broken_and_firm():
    L = Listing(listing_id="x", site="s", url="u", title="Gaming PC",
                description="Has some issues, needs diagnostic. Price is firm.")
    f = compute_flags(L)
    assert f.get("broken") is True
    assert f.get("firm") is True


def test_flag_firm_from_field():
    L = Listing(listing_id="x", site="s", url="u", title="PC", is_firm=True)
    assert compute_flags(L).get("firm") is True


def test_no_false_dealer_flag():
    L = Listing(listing_id="x", site="s", url="u", title="Custom gaming PC",
                description="Built it myself, RTX 3070, runs great.")
    assert "dealer" not in compute_flags(L)


def test_financial_reasons_not_a_dealer():
    # "financial reasons" (individual seller's motivation) must NOT flag as dealer
    L = Listing(listing_id="x", site="s", url="u", title="Gaming PC",
                description="Selling due to financial reasons, great condition.")
    assert "dealer" not in compute_flags(L)


def test_financing_available_is_a_dealer():
    L = Listing(listing_id="x", site="s", url="u", title="Gaming PC $680",
                description="Financing available, no credit needed, $40/week.")
    assert compute_flags(L).get("dealer") is True


def test_catalog_read_rejects_non_catalog(tmp_path):
    import pytest
    p = tmp_path / "random.csv"
    p.write_text("foo,bar\n1,2\n")
    with pytest.raises(ValueError, match="does not look like a deals catalog"):
        catalog.read(p)


# ---- catalog round-trip ----
def test_csv_roundtrip(tmp_path):
    L = Listing(
        listing_id="abc", site="offerup", url="u", title="Gaming PC, RTX 2070",
        price=425.0, previous_price=500.0, location_name="San Diego, CA",
        distance_mi=12.3, posted_at="2026-06-20T10:00:00+00:00",
        condition="Used", is_firm=False, image_urls=["http://a", "http://b"],
        query_matched="gaming pc", flags={"dealer": True},
        state="SOLD", is_sold=True, is_archived=False,
        raw_json=json.dumps({"tile": {"x": 1}}),
    )
    L.compute_price_drop()
    p = tmp_path / "cat.csv"
    catalog.write([L], p)
    back = catalog.read(p)
    assert len(back) == 1
    b = back[0]
    assert b.listing_id == "abc"
    assert b.price == 425.0
    assert b.previous_price == 500.0
    assert b.price_dropped is True
    assert b.price_drop_amount == 75.0
    assert b.image_urls == ["http://a", "http://b"]
    assert b.flags == {"dealer": True}
    assert b.is_firm is False
    assert b.state == "SOLD"
    assert b.is_sold is True and b.is_archived is False


def test_default_path_slug(tmp_path):
    from datetime import datetime, timezone
    when = datetime(2026, 6, 22, 14, 30, 0, tzinfo=timezone.utc)
    p = catalog.default_path(tmp_path, "offerup", "Gaming PC!!", when=when)
    assert p.name == "260622-143000-offerup-gaming-pc.csv"
