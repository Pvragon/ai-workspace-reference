"""Novelty scoring — LLM-as-judge with the three-baseline rubric.

Each item is scored 0-10 against three baselines:
  1. Intra-poll   — other items in this same poll (duplicate-announcement catch).
  2. Rolling corpus — recent digested items (did we cover this already?).
  3. Common knowledge — the model's own prior (intro rehashes / hype score low).

The judge returns a strict JSON object; the threshold split happens here.
"""
from __future__ import annotations

import json
from typing import Optional

from .record import Item, Verdict
from .gemini import generate_json, GeminiError

_RUBRIC = """\
You are the editorial filter for a working AI engineer (the operator). He builds agentic
developer tooling and ships production LLM systems. His time is scarce; you only
let through content that teaches something genuinely NEW or actionable.

Score the CANDIDATE item 0-10 on whether it is worth his time, judged against:
  (1) the OTHER items in this same batch (penalize duplicate coverage of the
      same announcement — the most substantive treatment wins, the rest lose),
  (2) the RECENTLY-DIGESTED items below (penalize anything already covered),
  (3) general AI-practitioner common knowledge (penalize intro rehashes, hype,
      reaction videos, and "this changes everything" with no substance).

HARD GATES — apply these BEFORE the rubric; any that trips caps the score:
  - NOT primarily in English  -> score 0, reason "non-English".
  - Marketing / customer story / testimonial / case-study / sponsor spot /
    product sizzle-reel with no reproducible technical content -> score <= 3,
    however polished or from whatever official source. Being an official launch
    is NOT substance; a launch only scores high if it teaches HOW something works
    or hands the viewer something they can act on.
  - PURE / academic research with no path to practice (pure theory,
    benchmark-chasing, model-internals or mathematics with no takeaway an
    engineer or operator can USE) -> score <= 4, reason "pure research, not
    actionable". We want USABLE findings only: applied research an AI builder can
    act on, and business / product / go-to-market METHODOLOGY. A research result
    passes only if it comes with a concrete technique, workflow, framework, or
    decision-relevant conclusion the viewer can apply.
  - Empty or unusable transcript -> score 0, reason "no usable transcript".

Rubric dimensions (each 0-10, then combine into the overall score):
  - novelty: new product / pattern / idea / finding, or a rehash?
  - specificity: does it teach HOW, or is it vague speculation?
  - credibility: is the creator showing real work, or just reacting/selling?
  - actionability: can the operator APPLY it to agentic dev, LLM tooling, or running
    the business? This is the heaviest dimension — weight it above the others.

Be a STRICT gatekeeper: the bar is "a usable finding, technique, or business /
methodology insight an AI builder can act on — genuinely new OR directly
applicable." Interesting-but-inapplicable does NOT pass. When unsure, score
lower — a false pass wastes his time more than a false reject.

Return STRICT JSON, no prose:
{
  "score": <int 0-10>,
  "reason": "<= 18 words, why it scored that way>",
  "summary": "<= 45 words, plain description of what this item IS and what a viewer gets from it — the content itself, not the score>",
  "key_points": ["3-5 concrete takeaways a reader gets without watching", "..."],
  "dimensions": {"novelty": <int>, "specificity": <int>, "credibility": <int>, "actionability": <int>}
}
"""


_PREFILTER = """\
You are pre-screening YouTube uploads for an AI engineer's digest, working ONLY
from channel name + title (no transcript yet). This is a RELEVANCE gate — it does
NOT decide how many we fetch (a separate budget does that). So judge relevance
honestly and rank the relevant ones.

RELEVANT: the title plausibly signals substantive AI / agentic-dev / LLM-tooling
content, OR AI-business / startup / product methodology — something new or
actionable. This INCLUDES LLM token economics / "tokenomics" / cost & token-
efficiency / model pricing & selection (core to AI engineering), agent
frameworks, evals, infra, and self-hosting/local AI. When genuinely unsure but
plausibly relevant, mark RELEVANT (the transcript makes the real call).
IRRELEVANT: clearly off-topic — general tech UNRELATED to AI (e.g. VPN reviews,
OS switching, generic cybersecurity), entertainment, pure clickbait with no
substance signal, or an obvious marketing/sponsor title.

Return ALL relevant indices, BEST FIRST (most promising / most likely-novel
first); omit the irrelevant ones. Do NOT cap the list — list every relevant item.
Return STRICT JSON: {"keep": [<relevant indices, best first>]}
"""


_PREFILTER_BATCH = 60   # keep each LLM call small & fast (big single calls time out)


_INTERESTS = """\
You are matching YouTube uploads to a user's stated PERSONAL-INTEREST topics,
working from channel name + title only. These topics surface videos the user
wants to see EVEN WHEN they are not industry-novel — a separate, additive signal
from the general relevance/novelty gate.

For each candidate, decide whether its title plausibly matches ANY of the
numbered TOPICS below. Be reasonably INCLUSIVE — if a title plausibly fits a
topic, match it (a later stage sees the description and can still confirm). Do
NOT match on generic AI relevance; match ONLY the specific interest topics.
Match each candidate to at most one topic (its best fit).

Return STRICT JSON mapping matched candidate indices to the 1-based topic number
they best match:
{"matches": {"<candidate index>": <topic number>, ...}}
Omit candidates that match no topic. No prose.
"""


def classify_interests(candidates: list[dict], topics: list[str], *,
                       model: str, api_key: str) -> dict[str, str]:
    """Title-level personal-interest matcher. Returns {uid: matched_topic_str}.

    Additive and non-blocking: on any LLM error it returns whatever it matched so
    far (fails CLOSED to "no match"), because interest is a bonus signal — the
    prefilter already owns the LLM-down defer decision for the poll as a whole.
    Batched like the prefilter so a big first run never times out."""
    if not candidates or not topics:
        return {}
    out: dict[str, str] = {}
    topic_block = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    for start in range(0, len(candidates), _PREFILTER_BATCH):
        chunk = candidates[start:start + _PREFILTER_BATCH]
        listing = "\n".join(f"{i}. [{c['producer']}] {c['title']}" for i, c in enumerate(chunk))
        prompt = (_INTERESTS + "\n\n=== TOPICS ===\n" + topic_block
                  + "\n\n=== CANDIDATES ===\n" + listing)
        try:
            obj = generate_json(prompt, model=model, api_key=api_key)
            matches = obj.get("matches", {})
        except GeminiError:
            break                                          # additive — keep what we have
        except (ValueError, TypeError):
            continue
        if isinstance(matches, dict):
            pairs = list(matches.items())
        elif isinstance(matches, list):                    # tolerate [{"i":..,"topic":..}]
            pairs = [(m.get("i"), m.get("topic")) for m in matches if isinstance(m, dict)]
        else:
            pairs = []
        for k, v in pairs:
            try:
                idx, tnum = int(k), int(v)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(chunk) and 1 <= tnum <= len(topics):
                out[chunk[idx]["uid"]] = topics[tnum - 1]
    return out


def _prefilter_chunk(chunk: list[dict], *, model: str, api_key: str) -> tuple[list[dict], list[dict]]:
    listing = "\n".join(f"{i}. [{c['producer']}] {c['title']}" for i, c in enumerate(chunk))
    prompt = _PREFILTER + "\n\n=== CANDIDATES ===\n" + listing
    try:
        obj = generate_json(prompt, model=model, api_key=api_key)
        idxs = [int(i) for i in obj.get("keep", []) if isinstance(i, (int, float))]
    except GeminiError:
        raise                                              # LLM down -> caller defers
    except (ValueError, TypeError):
        idxs = list(range(len(chunk)))                     # parsed but malformed -> keep all
    seen = set()
    relevant = []
    for i in idxs:
        if 0 <= i < len(chunk) and i not in seen:
            seen.add(i)
            relevant.append(chunk[i])
    irrelevant = [c for j, c in enumerate(chunk) if j not in seen]
    return relevant, irrelevant


def prefilter(candidates: list[dict], *, model: str, api_key: str
              ) -> tuple[list[dict], list[dict]]:
    """Title-only RELEVANCE gate. Returns (relevant_ranked, irrelevant).

    Batched (``_PREFILTER_BATCH`` titles/call) so no single request is large enough
    to time out — a first run can surface 300+ candidates. Relevance and budget are
    SEPARATE: returns every relevant item (ranked best-first within each batch); the
    caller applies the transcript budget. Only ``irrelevant`` is safe to mark seen.
    Propagates GeminiError so the caller can defer (never fails open on LLM down)."""
    if not candidates:
        return [], []
    relevant: list[dict] = []
    irrelevant: list[dict] = []
    for start in range(0, len(candidates), _PREFILTER_BATCH):
        chunk = candidates[start:start + _PREFILTER_BATCH]
        rel, irr = _prefilter_chunk(chunk, model=model, api_key=api_key)
        relevant.extend(rel)
        irrelevant.extend(irr)
    return relevant, irrelevant


_REFINE = """\
You are the SECOND-pass gate for an AI engineer's digest. Each item passed a
title screen; now you have the channel + title + DESCRIPTION (still no
transcript). Decide which genuinely deserve a transcript fetch — this is where we
catch items that looked relevant by title but the description reveals are
off-topic, a sponsor/marketing spot, a re-upload, or low-substance.

KEEP if the description confirms substantive AI / agentic-dev / LLM-tooling /
token-efficiency / AI-business / product-methodology content worth reading.
DROP if the description shows it is off-topic, mostly promotion/sponsor, or
clearly thin. When the description is empty/uninformative, KEEP (fall back to the
title screen). Rank kept BEST FIRST. Return STRICT JSON:
{"keep": [<indices to keep, best first>]}
"""


def refine_by_description(survivors: list[dict], *, model: str, api_key: str
                          ) -> tuple[list[dict], list[dict]]:
    """Second relevance gate using title + description. ``survivors`` items are
    {cand, description, ...}. Returns (kept, dropped). Fails OPEN (keep all)."""
    if not survivors:
        return [], []
    listing = "\n".join(
        f"{i}. [{s['cand']['producer']}] {s['cand']['title']}\n   desc: "
        f"{(s.get('description') or '(none)')[:280]}"
        for i, s in enumerate(survivors))
    prompt = _REFINE + "\n\n=== ITEMS ===\n" + listing
    try:
        obj = generate_json(prompt, model=model, api_key=api_key)
        idxs = [int(i) for i in obj.get("keep", []) if isinstance(i, (int, float))]
    except GeminiError:
        raise                                              # LLM down -> caller defers
    except (ValueError, TypeError):
        idxs = list(range(len(survivors)))
    seen = set()
    kept = []
    for i in idxs:
        if 0 <= i < len(survivors) and i not in seen:
            seen.add(i)
            kept.append(survivors[i])
    dropped = [s for j, s in enumerate(survivors) if j not in seen]
    return kept, dropped


def _context_block(recent: list[dict]) -> str:
    if not recent:
        return "(none yet — corpus is empty)"
    return "\n".join(
        f"- [{r.get('score','?')}] {r.get('title','')} — {r.get('producer','')}: {r.get('reason','')}"
        for r in recent
    )


def _siblings_block(siblings: list[Item], this_uid: str) -> str:
    others = [s for s in siblings if s.uid != this_uid]
    if not others:
        return "(this is the only item in the batch)"
    return "\n".join(f"- {s.producer}: {s.title}" for s in others)


def build_prompt(item: Item, siblings: list[Item], recent: list[dict],
                 transcript_max_chars: int) -> str:
    text = item.text[:transcript_max_chars] if item.text else ""
    return (
        f"{_RUBRIC}\n\n"
        f"=== OTHER ITEMS IN THIS BATCH ===\n{_siblings_block(siblings, item.uid)}\n\n"
        f"=== RECENTLY DIGESTED (rolling corpus) ===\n{_context_block(recent)}\n\n"
        f"=== CANDIDATE ===\n"
        f"source: {item.source}\nproducer: {item.producer}\ntitle: {item.title}\n"
        f"description: {(item.description or '')[:400]}\n"
        f"transcript:\n{text}\n"
    )


_DEEPEN = """\
You are writing a "skip the video" briefing for a busy AI engineer. He has
already decided this video is worth it; your job is to hand him the LEARNINGS so
he does not need to watch. Read the transcript and extract the substance.

Write for fast scanning. Be concrete and specific — name the tools, techniques,
numbers, and steps actually shown, not vague gestures ("discusses X"). If the
video teaches a workflow or setup, give the actual steps/ingredients. NO hype,
NO filler, NO restating the title.

Return STRICT JSON, no prose:
{
  "learnings": ["<concrete takeaway or step he can act on>", "... 4-8 bullets"],
  "why_novel": ["<what is genuinely new / why it matters vs. what he already knows>", "... 1-3 bullets"]
}
Keep the WHOLE thing under ~380 words. Each bullet a tight, standalone line.
"""


def deepen(item: Item, *, model: str, api_key: str, transcript_max_chars: int) -> dict:
    """Second-pass 'skip the video' briefing for a CHOSEN item. Returns
    {"learnings": [...], "why_novel": [...]}. Fails soft to {} on any LLM error —
    a missing deep-dive must never drop an item from the digest."""
    text = item.text[:transcript_max_chars] if item.text else ""
    prompt = (
        f"{_DEEPEN}\n\n=== VIDEO ===\n"
        f"producer: {item.producer}\ntitle: {item.title}\n"
        f"description: {(item.description or '')[:400]}\n"
        f"transcript:\n{text}\n"
    )
    try:
        obj = generate_json(prompt, model=model, api_key=api_key)
    except GeminiError:
        return {}
    learnings = [str(x).strip() for x in obj.get("learnings", []) if str(x).strip()][:8]
    why_novel = [str(x).strip() for x in obj.get("why_novel", []) if str(x).strip()][:3]
    return {"learnings": learnings, "why_novel": why_novel} if (learnings or why_novel) else {}


_LEARN = """\
You extract the LEARNINGS from a video so the reader gets the value WITHOUT
watching it. Topic-agnostic — could be AI, health, business, anything. Work only
from the transcript (and description). Be information-DENSE: no preamble, no "in
this video", no fluff, no restating the title. If the transcript is thin or the
video is pure entertainment with no learnings, say so briefly.

Write {min_w}-{max_w} words total. Return STRICT JSON:
{{
  "headline": "<= 12 words capturing the single most useful takeaway",
  "summary_md": "<Markdown. A 1-2 sentence thesis, then the key learnings as tight
   '- ' bullets (facts, steps, models, numbers, names — the substance), then an
   optional short 'Takeaways:' line with what to DO with it. Dense and skimmable.>"
}}
"""


def summarize_learnings(item: Item, *, min_words: int, max_words: int,
                        model: str, api_key: str, transcript_max_chars: int) -> Optional[dict]:
    """Concise information-dense 'learnings' summary of one video for `digest
    learn`. Returns {"headline","summary_md"} or None on LLM failure (caller then
    defers — does NOT mark the video seen, so it retries next run)."""
    text = item.text[:transcript_max_chars] if item.text else ""
    prompt = (
        _LEARN.format(min_w=min_words, max_w=max_words)
        + f"\n\n=== VIDEO ===\nchannel: {item.producer}\ntitle: {item.title}\n"
        + f"description: {(item.description or '')[:600]}\ntranscript:\n{text}\n"
    )
    try:
        obj = generate_json(prompt, model=model, api_key=api_key)
    except GeminiError:
        return None
    headline = str(obj.get("headline", "")).strip()
    summary = str(obj.get("summary_md", "")).strip()
    if not summary:
        return None
    return {"headline": headline or item.title, "summary_md": summary}


def score_item(item: Item, siblings: list[Item], recent: list[dict], *,
               model: str, api_key: str, threshold: int,
               transcript_max_chars: int) -> Verdict:
    prompt = build_prompt(item, siblings, recent, transcript_max_chars)
    try:
        obj = generate_json(prompt, model=model, api_key=api_key)
    except GeminiError as e:
        # Scoring failure -> route to rejects with a visible reason, don't crash.
        return Verdict(score=0, passed=False, reason=f"scoring error: {e}",
                       key_points=[], dimensions={}, error=str(e))
    try:
        sc = int(obj.get("score", 0))
    except (TypeError, ValueError):
        sc = 0
    sc = max(0, min(10, sc))
    return Verdict(
        score=sc,
        passed=sc >= threshold,
        reason=str(obj.get("reason", ""))[:200],
        summary=str(obj.get("summary", ""))[:400],
        key_points=list(obj.get("key_points", []))[:6],
        dimensions=obj.get("dimensions", {}) if isinstance(obj.get("dimensions"), dict) else {},
    )
