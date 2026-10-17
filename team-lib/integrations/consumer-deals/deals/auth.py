"""Per-site auth/device tokens, stored in ~/.config/deals/auth.json (gitignored).

OfferUp's read API does NOT validate the device token (VERIFIED 2026-06-22:
empty / garbage / minted tokens all return full results). So for OfferUp,
``refresh-auth`` simply MINTS a fresh ``web-<56 hex>`` token locally — no browser,
no session capture, "anyone can use it" out of the box.

The structure is kept generic (per-site dict) so future adapters that DO need a
real captured session (eBay / FB Marketplace) can store cookies/headers here and
the scraper's self-heal-on-401 path stays uniform. A Playwright capture helper is
provided as an optional fallback (requires the ``browser`` extra).
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from . import config

DEFAULT_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")


def auth_path() -> Path:
    return config.config_dir() / "auth.json"


def _load_all() -> dict:
    p = auth_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_all(data: dict) -> None:
    p = auth_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))
    os.chmod(p, 0o600)  # tokens are not secrets here, but keep them user-only


def get(site: str) -> Optional[dict]:
    return _load_all().get(site)


def set_site(site: str, record: dict) -> None:
    data = _load_all()
    data[site] = record
    _save_all(data)


def mint_offerup_token() -> dict:
    """Mint a fresh OfferUp web device token + session id. Pure-local."""
    token = "web-" + secrets.token_hex(28)            # web- + 56 hex chars
    session_id = f"{token}@{int(time.time() * 1000)}"
    return {
        "x-ou-d-token": token,
        "ou-session-id": session_id,
        "user-agent": DEFAULT_UA,
        "minted_at": int(time.time()),
    }


def refresh(site: str) -> dict:
    """(Re)provision auth for a site and persist it. Returns the new record."""
    if site == "offerup":
        rec = mint_offerup_token()
        set_site(site, rec)
        return rec
    raise NotImplementedError(f"refresh-auth not implemented for site '{site}'")


def ensure(site: str) -> dict:
    """Return stored auth for a site, minting/refreshing if absent."""
    rec = get(site)
    if rec:
        return rec
    return refresh(site)
