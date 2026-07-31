"""Adapter registry. Add a marketplace by registering its Adapter subclass here."""
from __future__ import annotations

from .base import Adapter
from .offerup import OfferUpAdapter

_REGISTRY = {
    OfferUpAdapter.site: OfferUpAdapter,
}


def get_adapter_cls(site: str):
    try:
        return _REGISTRY[site]
    except KeyError:
        raise ValueError(f"unknown site '{site}' (have: {', '.join(sorted(_REGISTRY))})")


def available_sites() -> list:
    return sorted(_REGISTRY)
