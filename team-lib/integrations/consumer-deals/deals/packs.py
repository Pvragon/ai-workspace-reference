"""Domain packs — the generic extractor + valuer + scorer (PACK_SPEC contract).

A *pack* is per-domain config/data: a regex extraction spec + guardrails, a value
table, and scoring knobs. This module is the **generic engine** that consumes any
pack — the CLI never changes per domain. It is deterministic and provider-free:
regex attribute extraction + table valuation + a generic deal score. (LLM-assisted
extraction for messy listings is the generator skill's job — the agent writes
attributes back into the catalog; this engine stays offline and testable.)

Pack layout: ``packs/<domain>/pack.toml`` + ``packs/<domain>/value.csv``.
Resolved from ``<config>/packs/<domain>`` first, then the repo's shipped ``packs/``.

HARD constraint (memory feedback_deal-mining-scam-flag-is-verify-not-verdict):
a too-good-to-be-true score is a VERIFY-tier signal (``flags.verify_tier``), never
an auto-drop. The engine flags; it never excludes.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import config
from .record import Listing

try:                                  # py311+
    import tomllib as _toml
except ModuleNotFoundError:
    import tomli as _toml             # type: ignore


class PackError(Exception):
    pass


@dataclass
class Pack:
    name: str
    meta: dict
    text_sources: list
    prefer_source: str
    skip_phrases: list
    regex: dict                       # field -> compiled pattern
    value_table: dict                 # feature -> {key -> (min, avg, max)}
    verify_tier_threshold: float
    attributes: dict                  # declared schema
    include_re: Optional[re.Pattern]  # listing must match to be in-domain
    exclude_re: Optional[re.Pattern]  # listing matching this is out-of-domain


def packs_dirs() -> list:
    """Search order: user packs, then the repo's shipped packs/."""
    return [config.config_dir() / "packs",
            Path(__file__).resolve().parent.parent / "packs"]


def _find_pack(name: str) -> Path:
    for base in packs_dirs():
        p = base / name
        if (p / "pack.toml").exists():
            return p
    raise PackError(f"no pack '{name}' (looked in {[str(d) for d in packs_dirs()]})")


def _load_value_csv(path: Path) -> dict:
    table: dict = {}
    if not path.exists():
        return table
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            feat = (row.get("feature") or "").strip().lower()
            key = (row.get("key") or "").strip().lower()
            if not feat or not key:
                continue
            try:
                table.setdefault(feat, {})[key] = (
                    float(row["min"]), float(row["avg"]), float(row["max"]))
            except (KeyError, ValueError):
                continue
    return table


def load_pack(name: str) -> Pack:
    root = _find_pack(name)
    data = _toml.loads((root / "pack.toml").read_text())
    ex = data.get("extract", {})
    regex = {}
    for fld, pat in (ex.get("regex", {}) or {}).items():
        try:
            regex[fld] = re.compile(pat, re.I)
        except re.error as e:
            raise PackError(f"pack '{name}' bad regex for {fld}: {e}")

    dom = data.get("domain", {})

    def _opt(pat):
        if not pat:
            return None
        try:
            return re.compile(pat, re.I)
        except re.error as e:
            raise PackError(f"pack '{name}' bad domain regex: {e}")

    return Pack(
        name=name,
        meta=data.get("meta", {}),
        text_sources=ex.get("text_sources", ["title", "description"]),
        prefer_source=ex.get("prefer_source", "title"),
        skip_phrases=[s.lower() for s in ex.get("skip_phrases", [])],
        regex=regex,
        value_table=_load_value_csv(root / "value.csv"),
        verify_tier_threshold=float(data.get("scoring", {}).get("verify_tier_threshold", 0.55)),
        attributes=data.get("attributes", {}),
        include_re=_opt(dom.get("include")),
        exclude_re=_opt(dom.get("exclude")),
    )


def in_domain(pack: Pack, listing: Listing) -> bool:
    """Is this listing the thing the pack is about? Gate on the TITLE only — the
    title declares what the item IS. (Gating on the description wrongly excludes
    towers that merely *mention* a monitor/keyboard/games in the body.) Coarse by
    design; the generator skill's LLM pass refines edge cases like bundles."""
    title = listing.title or ""
    if pack.exclude_re and pack.exclude_re.search(title):
        return False
    if pack.include_re and not pack.include_re.search(title):
        return False
    return True


# ---- extraction ----
def _clean_text(text: str, skip_phrases: list) -> str:
    """Drop clauses containing a skip phrase (e.g. 'upgrade to RTX 4090') so we
    don't mis-extract aspirational/compatibility mentions."""
    if not text:
        return ""
    parts = re.split(r"[.;\n!?]", text)
    kept = [p for p in parts if not any(sp in p.lower() for sp in skip_phrases)]
    return " . ".join(kept)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def extract(pack: Pack, listing: Listing) -> dict:
    sources = {"title": listing.title or "", "description": listing.description or "",
               "image_text": listing.image_text or ""}
    # prefer_source first, then the rest of text_sources
    order = [pack.prefer_source] + [s for s in pack.text_sources if s != pack.prefer_source]
    attrs: dict = {}
    for fld, pat in pack.regex.items():
        for src in order:
            text = _clean_text(sources.get(src, ""), pack.skip_phrases)
            m = pat.search(text)
            if m:
                attrs[fld] = _norm(m.group(0))
                break
    return attrs


# ---- valuation ----
def value(pack: Pack, attrs: dict) -> tuple:
    """Sum matched component values + a 'base' baseline. Requires at least one
    recognized value-driving component — we don't value a spec-less listing off
    the base alone (that's how a controller looked like a 'deal')."""
    mn = av = mx = 0.0
    matched = False
    for feat, key in attrs.items():
        row = pack.value_table.get(feat, {}).get(_norm(key))
        if row:
            matched = True
            mn += row[0]; av += row[1]; mx += row[2]
    if not matched:
        return (None, None, None)
    base = pack.value_table.get("base", {}).get("base")
    if base:
        mn += base[0]; av += base[1]; mx += base[2]
    return (round(mn, 2), round(av, 2), round(mx, 2))


def deal_score(price: Optional[float], est_avg: Optional[float]) -> Optional[float]:
    """(value - price) / value, clamped to [-1, 1]. >0 = below estimated value."""
    if price is None or not est_avg or est_avg <= 0:
        return None
    return round(max(-1.0, min(1.0, (est_avg - price) / est_avg)), 3)


def apply_pack(pack: Pack, listings: list) -> list:
    """Gate to in-domain, then extract attributes, value, score, and set the
    verify-tier flag. Out-of-domain listings are flagged and left unvalued
    (never dropped — the catalog stays complete). Mutates."""
    for L in listings:
        # reset prior pack-derived flags so re-valuing is idempotent
        L.flags = {k: v for k, v in (L.flags or {}).items()
                   if k not in ("verify_tier", "out_of_domain")}
        if not in_domain(pack, L):
            L.attributes = {}
            L.est_value_min = L.est_value_avg = L.est_value_max = None
            L.deal_score = None
            L.flags["out_of_domain"] = True
            continue
        attrs = extract(pack, L)
        L.attributes = attrs
        mn, av, mx = value(pack, attrs)
        L.est_value_min, L.est_value_avg, L.est_value_max = mn, av, mx
        L.deal_score = deal_score(L.price, av)
        # verify-tier: a too-good score is a HARD-VERIFY signal, never a drop
        if L.deal_score is not None and L.deal_score >= pack.verify_tier_threshold:
            flags = dict(L.flags or {})
            flags["verify_tier"] = True
            L.flags = flags
    return listings
