"""Catalog diff engine + delta CSV."""
import csv

from deals import diff
from deals.record import Listing


def _L(lid, price=None, title="t", state=None, is_sold=None):
    return Listing(listing_id=lid, site="offerup", url=f"u/{lid}", title=title,
                   price=price, state=state, is_sold=is_sold)


def test_new_gone_unchanged():
    old = [_L("a", 100), _L("b", 200)]
    new = [_L("b", 200), _L("c", 300)]
    r = diff.diff_catalogs(old, new)
    assert [L.listing_id for L in r.new] == ["c"]
    assert [L.listing_id for L in r.gone] == ["a"]
    assert [L.listing_id for L in r.unchanged] == ["b"]
    assert r.has_changes() is True   # c is new


def test_price_drop_and_rise():
    old = [_L("a", 500), _L("b", 300)]
    new = [_L("a", 400), _L("b", 350)]
    r = diff.diff_catalogs(old, new)
    assert len(r.price_drop) == 1 and len(r.price_rise) == 1
    drop = r.price_drop[0]
    assert drop.listing.listing_id == "a"
    assert drop.prev_price == 500 and drop.new_price == 400
    assert drop.delta == -100
    assert drop.pct == -20.0
    rise = r.price_rise[0]
    assert rise.delta == 50


def test_unknown_when_price_missing():
    old = [_L("a", None)]
    new = [_L("a", 100)]
    r = diff.diff_catalogs(old, new)
    assert len(r.unknown) == 1
    assert not r.price_drop and not r.price_rise


def test_no_changes():
    old = [_L("a", 100)]
    new = [_L("a", 100)]
    r = diff.diff_catalogs(old, new)
    assert r.has_changes() is False
    assert r.counts == {"new": 0, "gone": 0, "sold": 0, "unlisted": 0,
                        "price_drop": 0, "price_rise": 0, "unchanged": 1,
                        "unknown": 0}


def test_write_diff_csv(tmp_path):
    old = [_L("a", 500), _L("gone1", 99)]
    new = [_L("a", 400), _L("newb", 250)]
    r = diff.diff_catalogs(old, new)
    p = tmp_path / "delta.csv"
    diff.write_diff(r, p)
    rows = list(csv.DictReader(p.open()))
    by_change = {row["listing_id"]: row for row in rows}
    assert by_change["newb"]["change"] == "new"
    assert by_change["a"]["change"] == "price_drop"
    assert by_change["a"]["prev_price"] == "500"
    assert by_change["a"]["price_delta"] == "-100"
    assert by_change["a"]["price_change_pct"] == "-20.0"
    assert by_change["gone1"]["change"] == "gone"


def test_in_place_sold_transition():
    # listing present both runs, flips LISTED -> SOLD: it's `sold`, not unchanged/gone
    old = [_L("a", 400, state="LISTED")]
    new = [_L("a", 400, state="SOLD", is_sold=True)]
    r = diff.diff_catalogs(old, new)
    assert [L.listing_id for L in r.sold] == ["a"]
    assert not r.unchanged and not r.gone


def test_sold_takes_priority_over_price_change():
    # even with a price delta, a SOLD transition wins (availability beats price)
    old = [_L("a", 500, state="LISTED")]
    new = [_L("a", 400, state="SOLD", is_sold=True)]
    r = diff.diff_catalogs(old, new)
    assert [L.listing_id for L in r.sold] == ["a"]
    assert not r.price_drop


def test_in_place_unlisted_transition():
    old = [_L("a", 400, state="LISTED")]
    new = [_L("a", 400, state="UNLISTED")]
    r = diff.diff_catalogs(old, new)
    assert [L.listing_id for L in r.unlisted] == ["a"]
    assert not r.sold


def test_reclassify_gone_splits_sold_unlisted_gone():
    old = [_L("sold1", 300), _L("unl1", 250), _L("gone1", 99)]
    new = []                                  # everything left the feed
    r = diff.diff_catalogs(old, new)
    assert {L.listing_id for L in r.gone} == {"sold1", "unl1", "gone1"}
    lookup = {"sold1": "SOLD", "unl1": "UNLISTED", "gone1": None}  # gone1 -> null
    diff.reclassify_gone(r, lambda lid: lookup.get(lid))
    assert [L.listing_id for L in r.sold] == ["sold1"]
    assert [L.listing_id for L in r.unlisted] == ["unl1"]
    assert [L.listing_id for L in r.gone] == ["gone1"]
    assert r.sold[0].state == "SOLD" and r.sold[0].is_sold is True


def test_reclassify_gone_relisted_stays_gone():
    # a departed id that now resolves as LISTED again isn't sold/unlisted -> stays gone
    old = [_L("a", 100)]
    r = diff.diff_catalogs(old, [])
    diff.reclassify_gone(r, lambda lid: "LISTED")
    assert [L.listing_id for L in r.gone] == ["a"]
    assert not r.sold and not r.unlisted


def test_write_diff_includes_sold_and_state(tmp_path):
    old = [_L("s", 300, state="LISTED")]
    new = [_L("s", 300, state="SOLD", is_sold=True)]
    r = diff.diff_catalogs(old, new)
    p = tmp_path / "delta.csv"
    diff.write_diff(r, p)
    rows = {row["listing_id"]: row for row in csv.DictReader(p.open())}
    assert rows["s"]["change"] == "sold"
    assert rows["s"]["state"] == "SOLD"


def test_dedup_ids_last_wins():
    # defensive: duplicate ids in input collapse (catalogs already dedup, but be safe)
    old = [_L("a", 100), _L("a", 100)]
    new = [_L("a", 90)]
    r = diff.diff_catalogs(old, new)
    assert len(r.price_drop) == 1
