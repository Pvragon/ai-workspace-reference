"""Persist fetched transcripts to disk — one JSON per video.

Transcripts are large text blobs, so they live as files under
``$AI_DIGEST_CONFIG_DIR/transcripts/`` (like ``digests/``), NOT in the corpus DB
(which stays a lightweight seen-set + rolling-corpus). Persisting the raw text
lets a digest be re-synthesized without re-fetching (the transcript endpoint is
the guarded one) and is the substrate for future timestamp deep-links.

Schema is forward-compatible: ``segments`` is reserved for timed chunks
(``{start, text}``) once the fetch path stops flattening them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import config as cfg
from .record import Item


def _video_id(uid: str) -> str:
    """'youtube:abc123' -> 'abc123'. Falls back to the whole uid if unprefixed."""
    return uid.split(":", 1)[-1] if ":" in uid else uid


def path_for(uid: str) -> Path:
    return cfg.transcripts_dir() / f"{_video_id(uid)}.json"


def exists(uid: str) -> bool:
    return path_for(uid).exists()


def save(item: Item, *, fetched_at: str, score: Optional[int] = None,
         segments: Optional[list] = None) -> Path:
    """Write one transcript JSON. Overwrites any prior copy for the same video."""
    p = path_for(item.uid)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "uid": item.uid,
        "video_id": _video_id(item.uid),
        "source": item.source,
        "producer": item.producer,
        "title": item.title,
        "url": item.url,
        "published": item.published or "",
        "fetched_at": fetched_at,
        "score": score,
        "segments": segments or [],      # reserved for timed chunks
        "text": item.text or "",
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    return p


def load(uid: str) -> Optional[dict]:
    """Return the stored transcript dict for a uid, or None if absent/corrupt."""
    p = path_for(uid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (ValueError, OSError):
        return None


def load_recent(n: int = 12, *, since_iso: Optional[str] = None) -> list[dict]:
    """The ``n`` most recently fetched stored transcripts, newest first.

    This is the substrate for ``digest primer``: because every fetched transcript
    is already on disk, the primer can be re-run and re-tuned as often as you
    like without touching YouTube's guarded transcript endpoint at all.

    Sorted by the ``fetched_at`` field rather than file mtime — mtime lies as soon
    as anything rewrites a file.
    """
    d = cfg.transcripts_dir()
    if not d.exists():
        return []
    out = []
    for p in d.glob("*.json"):
        try:
            rec = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        if not (rec.get("text") or "").strip():
            continue
        if since_iso and (rec.get("fetched_at") or "") < since_iso:
            continue
        out.append(rec)
    out.sort(key=lambda r: r.get("fetched_at") or "", reverse=True)
    return out[:n] if n else out


def as_item(rec: dict) -> Item:
    """Rehydrate a stored transcript dict into an Item."""
    return Item(
        uid=rec.get("uid") or f"youtube:{rec.get('video_id','')}",
        source=rec.get("source") or "youtube",
        producer=rec.get("producer") or "",
        title=rec.get("title") or "",
        url=rec.get("url") or "",
        text=rec.get("text") or "",
        published=rec.get("published") or "",
    )


def save_many(items, *, fetched_at: str, scores: Optional[dict] = None) -> int:
    """Persist a batch of Items; returns count written. ``scores`` = {uid: score}."""
    scores = scores or {}
    n = 0
    for it in items:
        if it is None or not getattr(it, "text", ""):
            continue
        save(it, fetched_at=fetched_at, score=scores.get(it.uid))
        n += 1
    return n
