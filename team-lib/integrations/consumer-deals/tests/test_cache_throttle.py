"""Detail cache + rate limiter + circuit breaker + cache-first fill_details."""
import pytest

from deals import cache
from deals.throttle import RateLimiter, CircuitBreaker, ThrottledError, backoff_delay
from deals.record import Listing
from deals.adapters.offerup import OfferUpAdapter, NULL_BLOCK_THRESHOLD


# ---- cache ----
def test_cache_roundtrip():
    cache.set("offerup", "abc", {"price": "300"}, now=1000)
    assert cache.get("offerup", "abc", ttl=3600, now=1500) == {"price": "300"}


def test_cache_expiry():
    cache.set("offerup", "abc", {"x": 1}, now=1000)
    assert cache.get("offerup", "abc", ttl=100, now=1000 + 101) is None   # expired
    assert cache.get("offerup", "abc", ttl=None, now=1e12) == {"x": 1}     # ttl off


def test_cache_miss_and_stats_clear():
    assert cache.get("offerup", "nope") is None
    cache.set("offerup", "a", {"x": 1}); cache.set("offerup", "b", {"x": 2})
    assert cache.stats("offerup")["entries"] == 2
    assert cache.clear("offerup") == 2
    assert cache.stats("offerup")["entries"] == 0


# ---- rate limiter ----
def test_rate_limiter_spaces_requests():
    clock = {"t": 0.0}
    sleeps = []

    def fake_sleep(s):
        sleeps.append(s)
        clock["t"] += s

    rl = RateLimiter(rps=10, jitter=0, sleep=fake_sleep, clock=lambda: clock["t"])
    for _ in range(4):
        rl.acquire()
    # first acquire is free; each subsequent waits ~0.1s (1/10 rps)
    assert sleeps and all(abs(s - 0.1) < 1e-9 for s in sleeps)
    assert len(sleeps) == 3


def test_rate_limiter_disabled():
    rl = RateLimiter(rps=0, jitter=0, sleep=lambda s: pytest.fail("should not sleep"))
    rl.acquire(); rl.acquire()


# ---- circuit breaker ----
def test_circuit_breaker_trips_and_resets():
    cb = CircuitBreaker(threshold=3)
    assert cb.record_throttle() is False
    assert cb.record_throttle() is False
    assert cb.record_throttle() is True          # 3rd consecutive -> tripped
    with pytest.raises(ThrottledError):
        cb.check()


def test_circuit_breaker_success_resets():
    cb = CircuitBreaker(threshold=2)
    cb.record_throttle()
    cb.record_success()                          # reset
    assert cb.record_throttle() is False         # back to 1, not tripped
    cb.check()                                   # no raise


def test_backoff_grows_and_caps():
    assert backoff_delay(0, base=1, cap=30, jitter=0) == 1
    assert backoff_delay(2, base=1, cap=30, jitter=0) == 4
    assert backoff_delay(10, base=1, cap=30, jitter=0) == 30   # capped


# ---- cache-first fill_details ----
def _adapter(**kw):
    return OfferUpAdapter({"x-ou-d-token": "web-x", "ou-session-id": "web-x@1",
                           "user-agent": "ua"}, 32.8, -117.1, "92124", **kw)


def _detail(lid):
    return {"data": {"listing": {"listingId": lid, "title": "PC", "price": "300",
                                 "originalPrice": "300",
                                 "distance": {"value": 5.0, "unit": "MILE"}}}}


def test_fill_details_uses_cache_on_second_run(monkeypatch):
    a = _adapter()
    calls = {"n": 0}

    def fake_post(op, q, v, tries=3):
        calls["n"] += 1
        return _detail(v["id"])

    monkeypatch.setattr(a, "_post", fake_post)
    L1 = Listing(listing_id="z1", site="offerup", url="u", title="PC", raw_json="{}")
    a.fill_details([L1])
    assert calls["n"] == 1                        # fetched + cached

    L2 = Listing(listing_id="z1", site="offerup", url="u", title="PC", raw_json="{}")
    a.fill_details([L2])
    assert calls["n"] == 1                        # served from cache, no new fetch
    assert L2.distance_mi == 5.0                  # cached detail applied


def test_fill_details_refresh_bypasses_cache(monkeypatch):
    a = _adapter(refresh=True)
    calls = {"n": 0}
    monkeypatch.setattr(a, "_post", lambda op, q, v, tries=3: (calls.__setitem__("n", calls["n"] + 1) or _detail(v["id"])))
    L = Listing(listing_id="z2", site="offerup", url="u", title="PC", raw_json="{}")
    a.fill_details([L]); a.fill_details([L])
    assert calls["n"] == 2                        # refresh -> always fetch


def test_fill_details_throttle_stops_early(monkeypatch):
    a = _adapter()
    # every detail comes back empty (the soft-block signature)
    monkeypatch.setattr(a, "_post", lambda op, q, v, tries=3: {"data": {"listing": None}})
    stubs = [Listing(listing_id=f"n{i}", site="offerup", url="u", title="PC", raw_json="{}")
             for i in range(NULL_BLOCK_THRESHOLD + 20)]
    a.fill_details(stubs, concurrency=1)
    assert a.last_throttled is True
