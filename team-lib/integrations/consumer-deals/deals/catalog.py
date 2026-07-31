"""Catalog persistence — CSV for now (SQLite is the documented future for
recurring searches / price history).

A catalog is a CSV of normalized ``Listing`` rows. dict/list fields are
JSON-encoded in their cell; ``raw_json`` is preserved verbatim so no data is
lost. ``read``/``write`` round-trip cleanly.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .record import Listing, CSV_COLUMNS

_JSON_FIELDS = {"image_urls", "attributes", "flags"}
_BOOL_FIELDS = {"price_dropped", "is_firm", "is_sold", "is_archived"}


def _cell(name: str, value) -> str:
    if value is None:
        return ""
    if name in _JSON_FIELDS or name == "raw_json" and not isinstance(value, str):
        return json.dumps(value)
    if name in _JSON_FIELDS:
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write(listings: list, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for L in listings:
            d = L.to_dict()
            row = {k: _cell(k, d.get(k)) for k in CSV_COLUMNS}
            w.writerow(row)
    return path


def _uncell(name: str, raw: str):
    if raw == "":
        return None if name not in _JSON_FIELDS else ([] if name == "image_urls" else {})
    if name in _JSON_FIELDS:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return [] if name == "image_urls" else {}
    if name in _BOOL_FIELDS:
        return raw.lower() in ("true", "1", "yes")
    if name in ("price", "previous_price", "price_drop_amount", "price_drop_pct",
                "distance_mi", "est_value_min", "est_value_avg", "est_value_max",
                "deal_score"):
        try:
            return float(raw)
        except ValueError:
            return None
    return raw


_REQUIRED_COLUMNS = ("listing_id", "site", "url", "title")


def read(path: Path) -> list:
    path = Path(path)
    out = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        missing = [c for c in _REQUIRED_COLUMNS if c not in header]
        if missing:
            raise ValueError(
                f"{path} does not look like a deals catalog "
                f"(missing columns: {', '.join(missing)})")
        for row in reader:
            kwargs = {}
            for name in Listing.field_names():
                if name in row:
                    kwargs[name] = _uncell(name, row[name])
            out.append(Listing(**kwargs))
    return out


def default_path(catalogs_dir: Path, site: str, query: str,
                 when: Optional[datetime] = None) -> Path:
    when = when or datetime.now()   # local time: filename stamps match the user's day
    # ASCII-only slug so catalog filenames are portable across filesystems/tools
    slug = "".join(c if (c.isascii() and c.isalnum()) else "-"
                   for c in query.lower()).strip("-")[:40] or "query"
    stamp = when.strftime("%y%m%d-%H%M%S")
    base = Path(catalogs_dir) / f"{stamp}-{site}-{slug}.csv"
    # avoid clobbering a catalog written in the same second (back-to-back scrapes)
    path, n = base, 2
    while path.exists():
        path = base.with_name(f"{base.stem}-{n}{base.suffix}")
        n += 1
    return path


def latest(catalogs_dir: Path) -> Optional[Path]:
    d = Path(catalogs_dir)
    if not d.exists():
        return None
    cs = sorted(d.glob("*.csv"))
    return cs[-1] if cs else None


def recent(catalogs_dir: Path, n: int = 2) -> list:
    """The n most-recent catalogs, sorted oldest -> newest (timestamped names
    sort chronologically). Returns up to n paths."""
    d = Path(catalogs_dir)
    if not d.exists():
        return []
    cs = sorted(d.glob("*.csv"))
    return cs[-n:]
