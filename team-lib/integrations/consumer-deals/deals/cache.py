"""Persistent per-listing detail cache.

Makes detail fetching *rare* — the single biggest rate-limit defense:
  * re-runs and skill iterations reuse cached details (zero API calls)
  * a throttled / blocked run RESUMES from what it already fetched, instead of
    losing progress and re-hammering the endpoint
  * the pack-generator skill scrapes a sample ONCE, then iterates offline against
    the cache

Layout: ``<config_dir>/cache/<site>/<listing_id>.json`` — one small file per
listing, ``{"_cached_at": <epoch>, "data": <detail payload>}``, with a TTL.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from . import config

DEFAULT_TTL_S = 24 * 3600   # details are fairly stable intra-day; price moves are caught by re-scrape


def cache_dir(site: str) -> Path:
    return config.config_dir() / "cache" / site


def _path(site: str, listing_id: str) -> Path:
    return cache_dir(site) / f"{listing_id}.json"


def get(site: str, listing_id: str, ttl: Optional[float] = DEFAULT_TTL_S,
        now: Optional[float] = None) -> Optional[dict]:
    """Return the cached detail payload, or None if absent/expired/unreadable."""
    p = _path(site, listing_id)
    if not p.exists():
        return None
    try:
        rec = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if ttl is not None:
        age = (now if now is not None else time.time()) - rec.get("_cached_at", 0)
        if age > ttl:
            return None
    return rec.get("data")


def set(site: str, listing_id: str, data: dict, now: Optional[float] = None) -> None:
    p = _path(site, listing_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = int(now if now is not None else time.time())
    p.write_text(json.dumps({"_cached_at": stamp, "data": data}))


def stats(site: str) -> dict:
    d = cache_dir(site)
    files = list(d.glob("*.json")) if d.exists() else []
    return {"site": site, "entries": len(files), "dir": str(d)}


def clear(site: str) -> int:
    d = cache_dir(site)
    n = 0
    if d.exists():
        for f in d.glob("*.json"):
            f.unlink()
            n += 1
    return n
