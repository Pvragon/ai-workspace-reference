"""Source-agnostic content record + scoring verdict.

An ``Item`` is whatever an ingest adapter produces (a YouTube video, a blog
article, a Medium post, an X thread). Everything downstream — scorer, digest,
corpus — operates on ``Item`` and never branches on source type beyond grouping
the digest output.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Item:
    """One unit of content to score. ``uid`` is the stable dedupe key."""
    uid: str                      # stable id, e.g. "youtube:<videoId>"
    source: str                   # "youtube" | "blog" | "medium" | "x"
    producer: str                 # channel / author / publication display name
    title: str
    url: str
    text: str = ""                # transcript / article body / thread text
    description: str = ""         # channel/video description (cheap metadata, pre-transcript)
    published: Optional[str] = "" # ISO date if known (yt flat list omits it)

    def to_row(self) -> dict:
        d = asdict(self)
        d.pop("text", None)       # never persist full transcript in the corpus
        return d


@dataclass
class Verdict:
    """LLM novelty judgment for one Item."""
    score: int                    # 0-10
    passed: bool
    reason: str                   # one-line novelty justification (why this score)
    summary: str = ""             # <=50-word plain summary of what the item is/teaches
    key_points: list = field(default_factory=list)
    dimensions: dict = field(default_factory=dict)  # novelty/specificity/...
    error: Optional[str] = None   # set if scoring failed (item routed to rejects)
