"""Record price-drop derivation + post-filter logic."""
from datetime import datetime, timezone, timedelta

import pytest

from deals.record import Listing
from deals import filters


def _L(**kw):
    base = dict(listing_id="x", site="offerup", url="u", title="t")
    base.update(kw)
    return Listing(**base)


# ---- price drop ----
def test_price_drop_genuine():
    L = _L(price=300.0, previous_price=380.0)
    L.compute_price_drop()
    assert L.price_dropped is True
    assert L.price_drop_amount == 80.0
    assert L.price_drop_pct == pytest.approx(21.1, abs=0.1)


def test_price_increase_is_not_a_drop():
    L = _L(price=500.0, previous_price=300.0)  # price went UP
    L.compute_price_drop()
    assert L.price_dropped is False
    assert L.price_drop_amount is None
    assert L.price_drop_pct is None


def test_no_previous_price():
    L = _L(price=400.0, previous_price=None)
    L.compute_price_drop()
    assert L.price_dropped is False


# ---- age parsing ----
@pytest.mark.parametrize("spec,days", [
    ("30d", 30), ("6w", 42), ("2mo", 60), ("1y", 365), (" 3 mo ", 90),
])
def test_parse_age(spec, days):
    assert filters.parse_age(spec) == timedelta(days=days)


def test_parse_age_bad():
    with pytest.raises(ValueError):
        filters.parse_age("soon")


# ---- radius filter ----
def test_within_radius():
    assert filters.within_radius(_L(distance_mi=24.0), 40)
    assert not filters.within_radius(_L(distance_mi=41.0), 40)
    # unknown distance => excluded (can't prove in range)
    assert not filters.within_radius(_L(distance_mi=None), 40)


# ---- age filter ----
def test_within_age():
    now = datetime(2026, 6, 22, tzinfo=timezone.utc)
    recent = (now - timedelta(days=10)).isoformat()
    old = (now - timedelta(days=90)).isoformat()
    assert filters.within_age(_L(posted_at=recent), timedelta(days=60), now=now)
    assert not filters.within_age(_L(posted_at=old), timedelta(days=60), now=now)
    # unknown posted_at => kept (don't drop on age alone)
    assert filters.within_age(_L(posted_at=None), timedelta(days=60), now=now)


def test_age_epoch_millis():
    now = datetime(2026, 6, 22, tzinfo=timezone.utc)
    ms = str(int((now - timedelta(days=5)).timestamp() * 1000))
    assert filters.within_age(_L(posted_at=ms), timedelta(days=60), now=now)


def test_apply_combined():
    now = datetime(2026, 6, 22, tzinfo=timezone.utc)
    rows = [
        _L(distance_mi=10, posted_at=(now - timedelta(days=5)).isoformat()),   # keep
        _L(distance_mi=99, posted_at=(now - timedelta(days=5)).isoformat()),   # drop radius
        _L(distance_mi=10, posted_at=(now - timedelta(days=200)).isoformat()),  # drop age
    ]
    kept, dropped = filters.apply(rows, radius_mi=40, max_age="2mo", now=now)
    assert len(kept) == 1
    assert dropped == {"radius": 1, "age": 1}
