"""ai-digest — scheduled novelty-scored digest of AI content.

Phase 1: YouTube. Pulls new uploads from a curated channel list, scores each
transcript for novelty against a rolling corpus (LLM-as-judge), and emails a
digest of the signal with an auditable reject list.

Source-agnostic core: ingest adapters produce ``Item`` records; the scorer,
digest composer, and mailer never know which source an item came from. Blogs /
Medium / X plug in later as additional adapters (Phases 2-4).
"""
from __future__ import annotations

__version__ = "0.5.0"

from .record import Item  # noqa: E402,F401
