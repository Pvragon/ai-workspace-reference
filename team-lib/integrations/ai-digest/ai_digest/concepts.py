"""Concept-level extraction, clustering and trend ranking.

WHY THIS EXISTS
---------------
``score.py`` judges each *video* independently and the digest then emits one
summary per video. That architecture can only ever produce N summaries — it can
never answer "what genuinely new, impactful ideas showed up this week?", because
ideas do not live inside a single video. They live *across* videos.

This module changes the unit of analysis from the video to the **concept**:

  1. ``extract``  — pull atomic concepts out of ONE transcript (small prompt per
     video, so there is no 40k-token mega-prompt to time out; that was the
     silent-failure mode of ``brief.synthesize``).
  2. ``cluster``  — group concepts that are the same idea across videos. The
     count of DISTINCT PRODUCERS behind a cluster is the trend signal: five
     unrelated channels converging on one idea is a real trend, one channel
     saying it is noise. No per-video LLM score can see this.
  3. ``link``     — map this run's clusters onto the EXISTING ledger keys.
     Without this step the LLM mints a fresh slug for the same idea every run
     ("agent-self-approval" then "agents-approve-prs"), every concept looks NEW
     forever, and both the novelty and velocity signals are fiction. This is the
     load-bearing step for the whole ledger.
  4. ``rank``     — score clusters on source diversity x novelty x velocity x
     impact (pure arithmetic over the ledger, no LLM, so it is auditable).

All LLM calls are small and independently retryable; a failure degrades one
video's concepts rather than the whole run.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from . import config as cfg
from .gemini import generate_json, GeminiError
from .record import Item


# --- extraction cache -------------------------------------------------------
# Concept extraction is DETERMINISTIC per video: the transcript never changes, so
# re-extracting it every run is pure waste. Measured 2026-07-30: a 136-video
# window took ~35 min and 136 LLM calls, nearly all of them redundant. Cached
# per video (mirroring the transcripts/ store, one JSON per video), a run only
# pays for genuinely new transcripts — which is what makes a WIDE window
# affordable, and a wide window is what produces convergence at all.

def cache_path(uid: str):
    vid = uid.split(":", 1)[-1] if ":" in uid else uid
    return cfg.config_dir() / "concepts" / f"{vid}.json"


def load_cached(uid: str, *, version: int = 1) -> Optional[list]:
    """Cached concepts for a video, or None. A version bump invalidates every
    entry, so changing the extraction prompt cannot silently serve stale
    concepts extracted under the old rules."""
    p = cache_path(uid)
    if not p.exists():
        return None
    try:
        rec = json.loads(p.read_text())
    except (ValueError, OSError):
        return None
    if int(rec.get("version", 0)) != version:
        return None
    c = rec.get("concepts")
    return c if isinstance(c, list) else None


def save_cached(uid: str, concepts: list, *, version: int = 1) -> None:
    p = cache_path(uid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"uid": uid, "version": version,
                             "concepts": concepts}, ensure_ascii=False))


# Bump when the extraction prompt or concept shape changes materially.
EXTRACT_VERSION = 2

# --- extraction -------------------------------------------------------------

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "statement": {"type": "string"},
                    "kind": {"type": "string"},
                    "topic": {"type": "string"},
                    "specifics": {"type": "array", "items": {"type": "string"}},
                    "impact": {"type": "integer"},
                    "impact_reason": {"type": "string"},
                },
                "required": ["label", "statement", "kind", "impact"],
            },
        }
    },
    "required": ["concepts"],
}

# Closed topic taxonomy. Concepts are bucketed by topic and then clustered WITHIN
# each bucket. A single global clustering call over ~200 highly specific labels
# merged almost nothing (measured 2026-07-29: 209 concepts -> 204 clusters), which
# left the CONVERGENCE signal — the whole point of the ledger — dead on arrival.
# Bucketing first makes each clustering call small and topically pre-filtered, so
# "the same idea, worded differently" actually collides.
#
# Keep this list SHORT and STABLE: it is a routing key, not a description. Adding
# buckets makes collisions rarer, which is the failure being fixed.
TOPICS = [
    "agent-autonomy",          # agents acting without human approval gates
    "agent-orchestration",     # multi-agent, sub-agents, workflow topologies
    "agent-memory-context",    # context engineering, RAG, second brain, retrieval
    "agent-tooling",           # CLIs, IDEs, harnesses, MCP, agent dev ergonomics
    "evals-observability",     # testing, traces, debugging, benchmarking agents
    "coding-automation",       # code generation, PRs, review, refactor, migration
    "model-releases",          # new models and newly shipped capabilities
    "model-efficiency",        # small models, distillation, quantization, cost
    "training-methods",        # RL, SFT, post-training, curricula, fine-tuning
    "voice-multimodal",        # speech, vision, video, transcription
    "data-integration",        # pipelines, connectors, scraping, structured output
    "gtm-marketing",           # content, SEO, distribution, agentic go-to-market
    "business-monetization",   # pricing, business models, services, revenue
    "product-design-ux",       # design, UI generation, taste, product craft
    "infra-deployment",        # hosting, serving, local inference, ops
    "security-safety",         # prompt injection, sandboxing, alignment, risk
    "other",
]

_EXTRACT_PROMPT = """\
You are extracting IDEAS from a transcript, not summarizing the video.

Return 3-8 concepts. A concept is one atomic, transferable idea: a technique, a
tool capability, an empirical finding, a concrete news event, or a specific
prediction with a stated mechanism.

Rules:
- `label`: 3-6 words naming the idea in NEUTRAL, canonical terms. This label is
  the MATCHING KEY used to detect when different creators independently land on
  the same idea, so it must be phrased the way ANY creator covering it would.
  * NEVER put a product, brand, company, model or person name in the label.
    Those belong in `specifics` and `statement`. A label containing
    "VibeThinker-3B" can never match another video's label about the same
    underlying idea, which silently destroys the cross-source signal.
  * Prefer a plain noun phrase describing the CAPABILITY or TECHNIQUE, not the
    instance of it.
  * No hype words, no channel framing, no video title phrasing.
  GOOD: "agents approving their own code changes"
  GOOD: "small models matching large-model reasoning"
  BAD:  "Gumroad's insane new agent trick"       (brand + hype)
  BAD:  "VibeThinker-3B reasoning benchmarks"    (model name -> never matches)
- `statement`: ONE sentence stating the claim concretely, with the specifics in
  it (names, numbers, model ids). No hedging, no "the video discusses".
- `kind`: one of technique | tool | finding | news | prediction
- `topic`: EXACTLY one value from the TOPICS list given below. This is a routing
  key used to group related concepts, so pick the bucket another creator covering
  the same idea would also land in. If nothing fits, use "other".
- `specifics`: exact tool names, model ids, numbers, APIs, benchmarks mentioned.
- `impact`: 0-10 — does this CHANGE WHAT A PRACTITIONER SHOULD DO? 9-10 = act
  this week. 6-8 = changes how you'd design something. 3-5 = worth knowing.
  0-2 = commentary, hype, or restating common knowledge.
- `impact_reason`: <=15 words on why that impact number.

SKIP entirely: generic filler ("AI is moving fast"), channel self-promotion,
course/tool advertising, and anything that is already common knowledge to a
practitioner who follows the space.
"""

_EXTRACT_TOPICS_BLOCK = "TOPICS (pick exactly one per concept):\n" + "\n".join(
    f"  - {_t}" for _t in TOPICS)


def extract(item: Item, *, model: str, api_key: str,
            transcript_max_chars: int = 24000, log=None) -> list[dict]:
    """Extract atomic concepts from one item's transcript.

    Returns [] on LLM failure — one video's concepts are lost, never the run —
    but REPORTS the reason via ``log``. Degrading quietly is how brief.py died
    unnoticed for three polls.
    """
    text = (item.text or "")[:transcript_max_chars]
    if not text.strip():
        return []
    prompt = (
        f"{_EXTRACT_PROMPT}\n{_EXTRACT_TOPICS_BLOCK}\n"
        f"Return STRICT JSON: {{\"concepts\": [...]}}\n\n"
        f"=== VIDEO ===\ntitle: {item.title}\nchannel: {item.producer}\n"
        f"transcript:\n{text}\n"
    )
    try:
        obj = generate_json(prompt, model=model, api_key=api_key,
                            max_output_tokens=8192, thinking_budget=0)
    except GeminiError as e:
        if log:
            log(f"    ! extract failed ({item.producer}): {e}")
        return []
    out = []
    for c in (obj.get("concepts") or []):
        label = str(c.get("label", "")).strip()
        stmt = str(c.get("statement", "")).strip()
        if not label or not stmt:
            continue
        try:
            impact = max(0, min(10, int(c.get("impact", 0))))
        except (TypeError, ValueError):
            impact = 0
        topic = str(c.get("topic", "")).strip().lower()
        if topic not in TOPICS:          # never trust a free-text routing key
            topic = "other"
        out.append({
            "label": label,
            "statement": stmt,
            "topic": topic,
            "kind": str(c.get("kind", "")).strip().lower() or "finding",
            "specifics": [str(s) for s in (c.get("specifics") or [])][:8],
            "impact": impact,
            "impact_reason": str(c.get("impact_reason", "")).strip(),
            "uid": item.uid,
            "producer": item.producer,
            "title": item.title,
            "url": item.url,
        })
    return out


# --- clustering -------------------------------------------------------------

_CLUSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "members": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["label", "members"],
            },
        }
    },
    "required": ["clusters"],
}

_CLUSTER_PROMPT = """\
Below are concepts extracted from several different videos, each numbered.

Group the numbers that express THE SAME underlying idea, even when different
creators word it differently. Then give each group a canonical `label` (3-6
neutral words) that would still fit if another creator covered the same idea.

Rules:
- Only merge genuinely identical ideas. Two DIFFERENT techniques that happen to
  share a topic stay in SEPARATE groups. Over-merging destroys the signal.
- Every number must appear in exactly one group. A concept mentioned by only one
  video is a valid group of size 1 — do not force it into a neighbour.
- Prefer the clearest, most generic wording available among the members.
"""


def slug(label: str) -> str:
    """Stable-ish ascii slug for a concept label."""
    s = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return s[:64] or "unnamed"


def _cluster_bucket(concepts: list[dict], idxs: list[int], topic: str, *,
                    model: str, api_key: str, log=None) -> list[dict]:
    """Cluster ONE topic bucket. ``idxs`` are GLOBAL indices into ``concepts``.

    The model is shown local numbering 0..n-1 (small numbers cluster far more
    reliably than sparse global ones) and every returned index is mapped back
    through ``idxs``. Getting that mapping wrong would silently attribute an
    idea to the wrong video, so it is done in exactly one place.
    """
    listing = "\n".join(
        f"{local}. [{concepts[g]['producer']}] {concepts[g]['label']} — "
        f"{concepts[g]['statement']}"
        for local, g in enumerate(idxs)
    )
    prompt = (f"{_CLUSTER_PROMPT}\n"
              f"Every concept below is already known to share the topic "
              f"'{topic}', so look hard for genuine restatements of one idea "
              f"across different creators — but still keep DISTINCT techniques "
              f"apart.\nReturn STRICT JSON: "
              f"{{\"clusters\": [{{\"label\": str, \"members\": [int]}}]}}\n\n"
              f"=== CONCEPTS ({topic}) ===\n{listing}\n")
    try:
        obj = generate_json(prompt, model=model, api_key=api_key,
                            max_output_tokens=8192, thinking_budget=0)
        raw = obj.get("clusters") or []
    except GeminiError as e:
        if log:
            log(f"  ! clustering failed for '{topic}': {e} — that bucket stays "
                f"unclustered (its concepts keep their own labels)")
        raw = []
    if not raw:
        return [{"label": concepts[g]["label"], "members": [g], "topic": topic}
                for g in idxs]

    # Validate against LOCAL range, dedupe, then map local -> global.
    seen_local: set[int] = set()
    out = []
    for cl in raw:
        members = []
        for m in (cl.get("members") or []):
            try:
                m = int(m)
            except (TypeError, ValueError):
                continue
            if 0 <= m < len(idxs) and m not in seen_local:
                seen_local.add(m)
                members.append(idxs[m])
        label = str(cl.get("label", "")).strip()
        if members and label:
            out.append({"label": label, "members": members, "topic": topic})
    # Sweep anything the model forgot so no concept is ever silently lost.
    for local, g in enumerate(idxs):
        if local not in seen_local:
            out.append({"label": concepts[g]["label"], "members": [g],
                        "topic": topic})
    return out


def cluster(concepts: list[dict], *, model: str, api_key: str,
            log=None) -> list[dict]:
    """Group concepts across videos into idea clusters, bucketed by topic.

    One global clustering call over every concept does not work: measured
    2026-07-29, 209 concepts across 30 videos came back as 204 clusters, leaving
    the CONVERGING lane empty. Concepts are therefore routed into the closed
    ``TOPICS`` taxonomy at extraction time and clustered within each bucket, so
    each call is small and every candidate is already topically related.

    A failure in one bucket costs only that bucket's consolidation.
    """
    if not concepts:
        return []
    if len(concepts) == 1:
        c = concepts[0]
        return [{"label": c["label"], "members": [0],
                 "topic": c.get("topic", "other")}]

    buckets: dict[str, list[int]] = {}
    for i, c in enumerate(concepts):
        buckets.setdefault(c.get("topic") or "other", []).append(i)
    if log:
        shape = ", ".join(f"{k}:{len(v)}" for k, v in
                          sorted(buckets.items(), key=lambda kv: -len(kv[1])))
        log(f"  topic buckets → {shape}")

    out = []
    for topic, idxs in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        if len(idxs) == 1:               # nothing to cluster against
            g = idxs[0]
            out.append({"label": concepts[g]["label"], "members": [g],
                        "topic": topic})
            continue
        out.extend(_cluster_bucket(concepts, idxs, topic, model=model,
                                   api_key=api_key, log=log))
    return out


# --- ledger linking ---------------------------------------------------------

_LINK_SCHEMA = {
    "type": "object",
    "properties": {
        "links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cluster": {"type": "integer"},
                    "existing_key": {"type": "string"},
                },
                "required": ["cluster", "existing_key"],
            },
        }
    },
    "required": ["links"],
}

_LINK_PROMPT = """\
You are matching THIS RUN's idea clusters against a ledger of ideas already
tracked from previous runs.

For each new cluster, decide whether it is the SAME underlying idea as one of
the known ledger entries. Return `existing_key` = the ledger key it matches, or
the exact string "NEW" if this idea is not in the ledger.

This matters: a wrong "NEW" makes a months-old idea look brand new, and a wrong
match hides a genuinely new idea. When genuinely unsure, answer "NEW".
Match on the underlying idea, not on shared words — "agent memory" and "agent
observability" are different ideas even though both are about agents.
"""


def link_all(clusters: list[dict], known_for_topic, *, model: str, api_key: str,
             log=None) -> list[dict]:
    """Link clusters to the ledger ONE TOPIC AT A TIME.

    ``known_for_topic(topic)`` returns that bucket's ledger entries. Scoping by
    topic keeps each prompt small while remaining COMPLETE for its bucket — a
    flat global cap silently drops older ideas out of the prompt, and anything
    the linker cannot see is reported as NEW, which is precisely the fake-novelty
    failure linking exists to prevent.
    """
    by_topic: dict[str, list[dict]] = {}
    for cl in clusters:
        by_topic.setdefault(cl.get("topic") or "other", []).append(cl)
    out = []
    for topic, cls in by_topic.items():
        out.extend(link(cls, known_for_topic(topic), model=model,
                        api_key=api_key, log=log))
    return out


def link(clusters: list[dict], known: list[dict], *,
         model: str, api_key: str, log=None) -> list[dict]:
    """Assign each cluster a ledger ``key``, reusing an existing key when the
    idea is already tracked. Mutates and returns ``clusters``.

    ``known`` = [{"key": str, "label": str}, ...] from the corpus ledger.

    Without this the same idea gets a fresh slug every run and every concept
    looks NEW forever — the novelty and velocity signals become fiction. On LLM
    failure we fall back to exact-slug matching, which is conservative: it can
    miss a rename (over-reporting novelty) but never fabricates a match.
    """
    by_slug = {k["key"]: k for k in known}
    if not clusters:
        return clusters

    assigned: dict[int, str] = {}
    if known:
        listing_new = "\n".join(
            f"{i}. {cl['label']}" for i, cl in enumerate(clusters))
        listing_old = "\n".join(
            f"- {k['key']}: {k['label']}" for k in known[:400])
        prompt = (f"{_LINK_PROMPT}\nReturn STRICT JSON: "
                  f"{{\"links\": [{{\"cluster\": int, \"existing_key\": str}}]}}\n\n"
                  f"=== LEDGER (known ideas) ===\n{listing_old}\n\n"
                  f"=== THIS RUN'S CLUSTERS ===\n{listing_new}\n")
        try:
            obj = generate_json(prompt, model=model, api_key=api_key,
                                max_output_tokens=8192, thinking_budget=0)
            for ln in (obj.get("links") or []):
                try:
                    ci = int(ln.get("cluster"))
                except (TypeError, ValueError):
                    continue
                key = str(ln.get("existing_key", "")).strip()
                if 0 <= ci < len(clusters) and key and key != "NEW":
                    if key in by_slug:          # never invent a ledger key
                        assigned[ci] = key
        except GeminiError as e:
            if log:
                log(f"  ! ledger linking failed: {e} — falling back to exact-slug "
                    f"matching (novelty may over-report)")

    for i, cl in enumerate(clusters):
        if i in assigned:
            cl["key"] = assigned[i]
            cl["matched_existing"] = True
        else:
            s = slug(cl["label"])
            cl["key"] = s
            # exact-slug fallback still counts as a ledger hit
            cl["matched_existing"] = s in by_slug
    return clusters


# --- ranking ----------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "sources": 1.0,     # per distinct producer this run (capped) — CONVERGENCE
    "new": 2.5,         # first time this idea has ever appeared
    "velocity": 1.5,    # this run's mentions vs the trailing baseline
    "impact": 2.0,      # practitioner impact (0-1 normalized)
    "pioneer": 3.0,     # high-authority source alone and EARLY — see below
}

# Lanes. Convergence and earliness are DIFFERENT kinds of value and must not be
# collapsed into one number, or the primer cannot tell you which it is looking at.
LANE_CONVERGING = "converging"   # many independent sources — trend confirmed
LANE_EARLY = "early"             # few sources, high authority — brilliance pre-adoption
LANE_SINGLE = "single"           # one low-track-record source — probably noise


def authority(producer: str, trusted: set[str], prescience: dict) -> float:
    """0-1 credibility for a lone voice.

    Two inputs, in priority order:
      1. ``trusted`` — hand-listed creators whose solo signal counts. Needed to
         BOOTSTRAP: prescience is 0 for everyone until the ledger has history.
      2. ``prescience`` — EARNED from the ledger: of the concepts this producer
         was first to raise, what fraction later got corroborated by other
         producers? That is a leading-indicator track record, computed from data
         rather than curated by hand.
    """
    if producer in trusted:
        return 1.0
    return float((prescience or {}).get(producer, 0.0) or 0.0)


def rank(clusters: list[dict], concepts: list[dict], history: dict, *,
         weights: Optional[dict] = None, source_cap: int = 5,
         trusted: Optional[set] = None, prescience: Optional[dict] = None,
         converge_at: int = 3, ledger_cold: bool = False) -> list[dict]:
    """Attach trend metrics + a composite score to each cluster; sort desc.

    ``history`` maps concept key -> {"prior_mentions": int, "first_seen": str|None}
    where prior_mentions EXCLUDES this run. Pure arithmetic — no LLM — so the
    ranking is reproducible and auditable.

    Two independent routes to the top of the primer:

      CONVERGING — many independent producers said it. The trend is confirmed,
        but by definition you are hearing it after it spread.
      EARLY — ONE high-authority producer said it first. Unconfirmed, and the
        most valuable thing in the feed when it is right. Scored via the
        ``pioneer`` term, which applies only when the idea is new AND the source
        has standing, so a lone low-track-record voice still ranks as noise.

    A pure diversity score would systematically bury the second case. It is kept
    on a separate axis and surfaced in its own lane so the two are never
    confused for one another.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    trusted = trusted or set()
    prescience = prescience or {}
    out = []
    for cl in clusters:
        members = [concepts[i] for i in cl["members"]]
        producers = sorted({m["producer"] for m in members if m.get("producer")})
        hist = history.get(cl["key"], {}) or {}
        prior = int(hist.get("prior_mentions", 0) or 0)
        # Count distinct VIDEOS, not concept rows: one video that phrased the same
        # idea four ways is one mention, not four, or velocity inflates 4x.
        n_now = len({m.get("uid") for m in members if m.get("uid")}) or len(members)
        # On a cold ledger we cannot KNOW an idea is new — there is nothing to
        # have been seen against. Reporting "NEW" there is an unverifiable claim,
        # so novelty is treated as unknown (not asserted) until a baseline exists.
        is_new = (prior == 0 and not hist.get("first_seen")
                  and not ledger_cold)
        # velocity: how much louder is this idea now than its trailing baseline
        velocity = n_now / (prior if prior else 1)
        impact = max((m.get("impact", 0) for m in members), default=0)

        # Which producer actually earned the authority — reported in the output.
        # `producers` is sorted alphabetically, so using producers[0] would credit
        # whoever sorts first rather than whoever the lane is based on.
        ranked_by_auth = sorted(
            ({"p": m.get("producer"),
              "a": authority(m.get("producer"), trusted, prescience)}
             for m in members if m.get("producer")),
            key=lambda d: -d["a"])
        best_auth = ranked_by_auth[0]["a"] if ranked_by_auth else 0.0
        top_producer = ranked_by_auth[0]["p"] if ranked_by_auth else ""
        # Pioneer credit: EARLY (few sources) + NEW (nobody has said it before)
        # + a source with standing. Deliberately does not require corroboration —
        # that is the whole point of a leading indicator.
        is_early = len(producers) < converge_at
        # COLD LEDGER GUARD: with no history, EVERY concept reads as new, so
        # pioneer would fire for every trusted-source concept and the primer
        # becomes "whatever my favourite channels said". Novelty is only
        # meaningful against a baseline, so withhold pioneer credit until the
        # ledger has one. Measured on the first real run: 4/4 dives came from
        # 2 trusted channels before this guard existed.
        pioneer = best_auth if (is_early and is_new) else 0.0

        if len(producers) >= converge_at:
            lane = LANE_CONVERGING
        elif pioneer > 0 or best_auth >= 0.5:
            lane = LANE_EARLY
        else:
            lane = LANE_SINGLE

        score = (w["sources"] * min(len(producers), source_cap)
                 + w["new"] * (1.0 if is_new else 0.0)
                 + w["velocity"] * min(velocity, 4.0)
                 + w["impact"] * (impact / 10.0)
                 + w["pioneer"] * pioneer)
        out.append({
            **cl,
            "concepts": members,
            "producers": producers,
            "n_sources": len(producers),
            "n_mentions": n_now,
            "prior_mentions": prior,
            "first_seen": hist.get("first_seen"),
            "is_new": is_new,
            "novelty_known": not ledger_cold,
            "velocity": round(velocity, 2),
            "impact": impact,
            "authority": round(best_auth, 3),
            "top_producer": top_producer,
            "pioneer": round(pioneer, 3),
            "lane": lane,
            "score": round(score, 3),
        })
    out.sort(key=lambda c: (-c["score"], -c["n_sources"], c["label"]))
    return out


def prescience_scores(first_raises: dict, *, min_firsts: int = 3) -> dict:
    """Earned leading-indicator track record per producer.

    ``first_raises`` maps producer -> {"firsts": int, "corroborated": int} where
    `firsts` counts concepts this producer raised BEFORE anyone else and
    `corroborated` counts how many of those were later picked up by other
    producers. The ratio is "when this person is early, how often are they
    right?" — which is exactly the signal a diversity-only score throws away.

    Producers below ``min_firsts`` score 0: with one or two data points the ratio
    is noise, and a lucky single hit should not mint permanent authority.
    """
    out = {}
    for producer, d in (first_raises or {}).items():
        firsts = int((d or {}).get("firsts", 0) or 0)
        corrob = int((d or {}).get("corroborated", 0) or 0)
        if firsts >= min_firsts:
            out[producer] = round(min(1.0, corrob / firsts), 3)
    return out
