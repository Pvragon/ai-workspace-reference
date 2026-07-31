"""Per-query watch state — the pointer that lets ``deals watch`` diff a query
against *its own* previous run (not just the two most-recent files of any query).

Light JSON now (SQLite is the documented future). One file per
``(site, query, location)`` key under ``<config_dir>/watch/``:

    {
      "key": "offerup|gaming pc|92124",
      "last_catalog": "/.../catalogs/260625-...-offerup-gaming-pc.csv",
      "last_run": "2026-06-25T12:00:00+00:00",
      "seen_count": 312
    }

``last_catalog`` is the prior catalog for this key; ``watch`` reads it, diffs the
fresh scrape against it, then repoints it. The incremental poll only sees the
feed *head*, so it upserts into the prior catalog rather than replacing it (a
listing missing from the head isn't gone — it's just below the fold).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config


def watch_dir() -> Path:
    d = config.config_dir() / "watch"
    d.mkdir(parents=True, exist_ok=True)
    return d


def key(site: str, query: str, location: str) -> str:
    return f"{site}|{query.strip().lower()}|{location}"


def _slug(k: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", k.lower()).strip("-")[:80] or "key"


def _path(k: str) -> Path:
    return watch_dir() / f"{_slug(k)}.json"


def load(k: str) -> dict:
    p = _path(k)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def last_catalog(k: str) -> Optional[Path]:
    rec = load(k)
    lc = rec.get("last_catalog")
    if lc and Path(lc).exists():
        return Path(lc)
    return None


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def save(k: str, last_catalog_path: Path, seen_count: int,
         when: Optional[str] = None) -> Path:
    p = _path(k)
    p.write_text(json.dumps({
        "key": k,
        "last_catalog": str(last_catalog_path),
        "last_run": when or now_iso(),
        "seen_count": seen_count,
    }, indent=2))
    return p
