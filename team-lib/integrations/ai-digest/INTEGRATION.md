---
template: integration
version: 0.5.1
summary: "ai-digest CLI (command `digest`) — scheduled novelty-scored digest of AI content. Phase 1 YouTube: yt-dlp lists new uploads, youtube-transcript-api pulls captions, Gemini 2.5-flash scores novelty against a rolling SQLite corpus, gws emails a digest with an auditable reject list. Also `digest learn`: per-video learnings emails for curated playlists."
created: 2026-06-29
last_updated: 2026-08-01
maintainer: your-agent
status: active
---

# ai-digest

Command: `digest`. Standalone CLI at `team-lib/integrations/ai-digest/`
(install `pip install -e .` in its `.venv`).

## What it does

Scheduled pipeline that pulls new content from curated AI sources, scores each
for genuine novelty (LLM-as-judge against a rolling corpus), and emails a digest
of the signal with a visible reject list. **Phase 1 = YouTube** (built
2026-06-29). Blogs / Medium / X are future adapters on the same source-agnostic
core.

## Pipeline

`yt-dlp (new uploads) → youtube-transcript-api (captions) → corpus.filter_new
(SQLite seen-set) → Gemini 2.5-flash 3-baseline novelty rubric → threshold split
→ digest compose (grouped by source, + reject list) → gws gmail +send → corpus.record`

## Commands

- `digest init` — scaffold `~/.config/ai-digest` + seed channels
- `digest poll [--dry-run|--no-email] [--limit N] [--model M]` — run the pipeline
- `digest channels` / `digest stats` / `digest export`
- `digest learn [--dry-run|--no-email] [--limit N] [--force]` — summarize each
  NEW video in the `[learn.playlists]` playlists; one email per video, no
  novelty filtering (you curated it by adding it). Hourly cron at `:15`.

`run(dry_run, no_email, limit, model)` in `ai_digest.cli` is the chainable
programmatic entrypoint.

## `digest primer` — concept-level rapid primer (0.5.0)

Changes the unit of analysis from the VIDEO to the IDEA, targeting a <=5 minute
read. Pipeline:

`stored transcripts -> extract concepts (1 small call/video) -> cluster across
videos -> link to ledger -> rank -> compose (word cap enforced in code)`

Reads only from `transcripts/`, so it makes NO network calls and can be re-run
and re-tuned freely: `digest primer --dry-run -n 30`.

Scheduled by `cron-primer.sh` at **11:00 M/W/F** — after the 07:30 poll has
landed its transcripts (the poll paces fetches ~10 min apart, so a 15-fetch poll
can run ~2.5h). Because the primer never touches YouTube, its cadence carries no
block risk. `PRIMER_N` overrides how many recent transcripts it draws from.

Two independent routes to the top, kept on separate axes and labelled in the
output so they are never confused:

- **CONVERGING** — many independent creators carried the idea. Trend confirmed,
  but you are hearing it after it spread.
- **EARLY** — one high-authority creator said it FIRST. Unconfirmed, and the most
  valuable item in the feed when right. Scored by the `pioneer` weight, which
  requires novelty AND standing, so a lone no-track-record voice stays noise.

Authority is seeded by `[primer].trusted_sources` and then EARNED: the ledger
records who raised each idea first and whether others later picked it up, which
`prescience_scores` turns into a per-creator track record.

### Clustering + convergence (solved; needs a WIDE window)

Concepts are routed into the closed ``concepts.TOPICS`` taxonomy at extraction
time, then clustered WITHIN each bucket. Convergence turned out to depend on
corpus size at least as much as on the algorithm. Measured on the same store:

| window | clustering | merge rate | CONVERGING |
|---|---|---|---|
| 30 videos | one global call | 209 -> 204 (2%) | 0 |
| 30 videos | topic-bucketed | 194 -> 171 (12%) | 1 |
| 136 videos | topic-bucketed | 790 -> 536 (32%) | **24** |

Both changes were needed. A single global clustering call over ~200 highly
specific labels merges almost nothing; and even bucketed, 30 videos across ~25
channels simply do not contain enough overlap for creators to collide.

**Practical consequence: run the primer over a WIDE window.** `cron-primer.sh`
defaults to `-n 120`. A narrow window does not just weaken the trend signal, it
reports a *false* one — an idea covered by three creators looks single-source if
two of them fall outside the window.

This is affordable only because concept extraction is cached per video
(`config/concepts/`, one JSON each, invalidated by `EXTRACT_VERSION`). Extraction
is deterministic, so a run pays only for transcripts fetched since the last one.
Without the cache a 136-video window costs ~35 min and 136 LLM calls per run.

Caveat that still stands: more merging is not automatically better. Aggressive
merging blurs the canonical label into mush, so the bucket prompt still refuses
to merge distinct techniques. A large single-source tail (447 of 536 at full
corpus) is expected and largely real — most videos carry channel-specific
specifics that genuinely nobody else covered.

### Live validation (2026-07-30)

First real end-to-end runs over 136 stored transcripts:

- **Run 1** (cold): 788 concepts -> 546 ideas, 21 converging, 337-word primer
  emailed, ledger seeded with 546 concepts / 721 mentions. Top items were
  genuinely convergent — "multi-agent orchestration" carried 12 independent
  sources, "automated agent workflows" 9.
- **Run 2** exposed a real bug: `546 known ideas · 0 matched · 502 new`. Run 1
  had written the ledger before the `topic` column existed, so every row was
  NULL and the topic-scoped lookup matched none of them — the ledger silently
  reset its own history. NULL-topic rows are now visible from every bucket, and
  the live ledger was backfilled from the cached extractions.
- **Run 3** (after the fix + backfill) confirmed the ledger works end to end:
  `546 known ideas · 509 matched · 7 new`, 28 converging, and velocity tags
  (`▲2.5x`) appearing for the first time. Earned prescience produced its first
  real scores — Nate B Jones 0.67, Devsplainers 0.50, Y Combinator 0.43 — i.e.
  of the ideas each raised FIRST, the fraction others later picked up.
- **Cache**: runs 2 and 3 reported `extraction: 1 fresh, 135 cached`, turning a
  ~35 min run into minutes.

Lesson worth keeping: this class of bug is invisible to unit tests and to a
single run. It only appears on the SECOND run against a ledger the FIRST run
wrote. Any change to the ledger schema or the linking path should be validated by
two consecutive live runs, checking that `matched` is non-zero.

### Cold-ledger guard

On a ledger with no history every concept reads as new, so novelty is treated as
UNKNOWN rather than asserted: pioneer credit is withheld, ranking falls back to
sources/impact, and the output omits the `NEW` tag entirely (`ledger is COLD` in
the log). Without the credit guard, run #1 ranked purely on "which trusted
channel talked" — measured: 4/4 dives from 2 trusted channels. Without the tag
guard, the first primer labelled all 546 ideas `NEW`, a claim it had no baseline
to support.

## Finding the `learn` emails in Gmail

Every `digest learn` subject is `📝 <subject_tag> <video title>`, where
`subject_tag` comes from `[learn].subject_tag` in config (default
`AI Summary:`). Search it as a **quoted phrase**:

```
subject:"AI Summary"
```

- Bare `subject:summary` is useless — 301 hits in the maintainer's mailbox.
- **Never search the 📝 emoji.** Gmail strips emoji from queries, so
  `subject:📝` matches the entire mailbox.
- These emails are self-sent (from == to), so they may carry `SENT` without
  `INBOX` and never appear in the inbox. Search with `in:anywhere`.
- Pre-2026-07-29 summaries predate the tag; find them via the body phrase
  `"Video learnings"`.

## Dependencies / secrets

- `python3`, `yt-dlp`, `youtube-transcript-api` (Gemini called over plain REST).
- `GEMINI_FREE_API_KEY` in `personal/secrets/.env`; `gws` on PATH for email.

## Gotchas (verified 2026-06-29)

- YouTube `feeds/videos.xml` RSS returns 404 from server hosts — use yt-dlp flat
  extraction instead (it's also the transcript fallback).
- Gemini free tier: `gemini-2.5-flash` works in JSON mode; `gemini-2.0-flash`
  429s. Scoring retries 429/5xx with backoff.
- Videos without captions are logged + skipped, never fatal.

Schedule: `cron-poll.sh` M/W/F 07:30 · `cron-learn.sh` hourly at :15 ·
`cron-primer.sh` M/W/F 11:00. Read-only ingestion; the only outbound actions are
the digest, learnings and primer emails to the configured recipient.
