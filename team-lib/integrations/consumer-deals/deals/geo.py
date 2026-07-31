"""Geo helpers.

Two jobs:
  1. Resolve the user's OWN zip -> (lat, lon) ONCE (at ``deals init``), via the
     free Zippopotam.us API (no key). Cached in config; manual override allowed.
  2. Build the unsigned ``userdata`` JWT that OfferUp's detail query reads to
     compute per-listing ``distance`` (see deals.adapters.offerup). This is why
     we never need a per-listing geocoder or a zip-centroid database.

A haversine is included as a generic fallback for adapters that DO expose
lat/lon per listing (OfferUp does not).
"""
from __future__ import annotations

import base64
import http.client
import json
import math
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Tuple


def geocode_zip(zipcode: str, country: str = "us", timeout: int = 15
                ) -> Optional[Tuple[float, float, str]]:
    """Resolve a postal code to (lat, lon, place_name) via Zippopotam.us.
    Returns None on failure (caller should prompt for manual lat/lon)."""
    zipcode = (zipcode or "").strip()
    if not zipcode:
        return None
    # URL-encode so stray characters can't produce an InvalidURL crash
    url = f"https://api.zippopotam.us/{country}/{urllib.parse.quote(zipcode)}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            d = json.load(r)
        place = d["places"][0]
        lat = float(place["latitude"])
        lon = float(place["longitude"])
        name = f"{place['place name']}, {place['state abbreviation']}"
        return lat, lon, name
    except (urllib.error.URLError, http.client.HTTPException,
            KeyError, IndexError, ValueError, TimeoutError):
        return None


def _b64url(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode().rstrip("=")


def build_userdata_jwt(lat: float, lon: float, zipcode: str = "") -> str:
    """Build the unsigned (alg:none) userdata JWT OfferUp uses to localize
    distance. VERIFIED 2026-06-22: plain base64 is ignored; the JWT shape is
    required. payload = {"location": {...}}."""
    header = {"alg": "none"}
    payload = {"location": {"zipCode": str(zipcode), "latitude": lat, "longitude": lon}}
    return f"{_b64url(header)}.{_b64url(payload)}."


def haversine_mi(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Great-circle distance in miles between (lat, lon) points. Generic fallback."""
    R = 3958.8
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))
