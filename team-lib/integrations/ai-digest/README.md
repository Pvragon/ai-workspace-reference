# ai-digest

Scheduled, novelty-scored digest of AI content. Pulls new uploads from a curated
list of sources, scores each for genuine novelty against a rolling corpus
(LLM-as-judge), and emails a digest of the signal — with an **auditable reject
list** so the filter is never a black box.

**Phase 1 (built): YouTube.** Blogs / Medium / X plug in later as adapters.

## Why

Staying on the edge of AI tooling is a practitioner's moat, but most of what gets
posted is recycled. This converts "hours of scrolling for the 1-in-10 video with
a genuinely new idea" into "one short digest, 3×/week."

## Install

```bash
cd team-lib/integrations/ai-digest
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/digest init           # scaffolds ~/.config/ai-digest + seeds channels
```

Requires `GEMINI_FREE_API_KEY` in `~/ai-workspace/personal/secrets/.env`
(already present in this workspace) and the `gws` CLI on PATH for email.

## Use

```bash
digest channels                 # show configured channels
digest poll --dry-run           # score + print digest; no email, no corpus write
digest poll                     # full run: ingest → score → digest → email
digest poll --no-email          # write the digest file but don't send
digest poll --limit 2           # only the first N channels (handy for testing)
digest doctor                   # offline health check: config, secrets, cookies, cooldown
digest doctor --probe           # + ONE transcript request to check block status (safe)
digest stats                    # corpus counts
digest export                   # reprint the most recent digest
digest forget <keyword>         # drop seen items matching keyword so they can resurface
digest reset --seen [--yes]     # clear the whole seen-set for a one-time clean-slate rerun
digest learn                    # summarize NEW videos in your learnings playlists
digest learn --dry-run          # list + summarize to stdout, no email
```

### Playlist learnings (`digest learn`)

A second, independent mode: **you** curate videos by adding them to a playlist, and
each new one gets a concise **200–500 word, information-dense learnings summary**
emailed to you — the value without watching. Unlike `poll`, there's **no filtering**
(you already curated) and it's **topic-agnostic** (AI, health, business, anything).

Setup: make an **unlisted** YouTube playlist, add it under `[[learn.playlists]]` in
config, and add videos to it from anywhere. `digest learn` (hourly cron) lists each
playlist, diffs against a separate seen-set (`learn:<id>`), fetches the **full**
transcript (not truncated — Gemini's 1M-token window), summarizes, and sends **one
email per video**. Videos without captions get a short "couldn't transcribe" note.
It shares the transcript rate-limiter / cookies / cooldown with `poll`, so the two
never collide or trip the guard.

### Personal interests (★ For you)

The `[interests]` config section holds a `topics` list. Items whose title/description
matches any topic are treated as an **additive** signal, separate from novelty: they
are never dropped as off-topic, bypass the recency window, are prioritized for the
transcript budget, and surface in a dedicated **★ For you** digest section (so novelty
scoring stays clean and you see *why* each one is there). Remove a topic and its videos
stop appearing; run `digest forget <keyword>` to let an already-seen video resurface
after adding a topic.

Run `digest doctor` before a first poll (or when debugging a block) — it verifies
config, the Gemini key, gws, cookie validity, and cooldown state without touching
the network. `--probe` adds a single live transcript request to confirm whether
YouTube is currently blocking you (one call is safe; bans come from volume).

`--dry-run` is freely repeatable while tuning — it never touches the corpus, so
the same videos re-score every time. A normal `poll` records every scored item
(passes feed the rolling-corpus baseline) so nothing is re-judged next poll.

## How it works

Four stages of escalating cost, so the **transcript endpoint** (the one YouTube
IP-blocks) is only ever hit for a small, twice-vetted, rate-paced shortlist:

```
cron (M/W/F)
  1. SCAN       yt-dlp flat listing across ALL channels → new titles
                (1 request/channel; safe endpoint, never blocked)
  2. TITLE GATE Gemini relevance on channel+title (no YouTube). Off-topic → seen
                + "skipped" audit; relevant ranked best-first.
  3. ENRICH +   one watch-page GET per top candidate → description + date (page
     DESC GATE  path, NOT the transcript endpoint). Gemini re-checks with the
                description and drops marketing/off-topic the title missed —
                BEFORE any transcript is spent. Recency applied here.
  4. TRANSCRIBE transcripts for the vetted shortlist, budgeted by the rate limiter
                and PACED ~transcript_min_interval_sec apart. abort-on-block.
  → score (Gemini, 3-baseline novelty rubric + description) → threshold split
  → digest (HTML tables: Worth your time / Rejected / Skipped) → gws gmail +send
  → corpus: passes feed novelty baselines; touched items marked seen; deferred
            (relevant-but-over-budget) left unseen for next poll.
```

So a 39-channel poll makes ≤`max_transcripts_per_poll` transcript requests, and
each is title-vetted, description-vetted, and spaced — the guard surface is tiny.

The core is **source-agnostic**: adapters emit `Item` records; the scorer, digest
composer, corpus, and mailer never branch on source type beyond grouping output.
Adding a source = adding one adapter that yields `Item`s.

### Three-baseline novelty rubric

Each item is scored 0–10 against: (1) **other items in the same poll** (kills
duplicate coverage of one announcement), (2) the **rolling corpus** of recently
digested items (kills "we covered this three weeks ago"), and (3) **general
practitioner common knowledge** (kills intro rehashes and hype). Dimensions:
novelty, specificity, credibility, actionability.

## Config

`~/.config/ai-digest/config.toml` (scaffolded by `digest init`). Everything is
editable — channels, threshold, model, recipient, transcript truncation, corpus
context size. Override the dir with `$AI_DIGEST_CONFIG_DIR`.

Alongside it: `corpus.db` (seen-set + rolling corpus), `digests/` (one rendered
digest per poll), and `transcripts/` (raw transcript JSON per fetched video, one
file each — set `persist_transcripts = false` to disable). Persisted transcripts
let a digest be re-synthesized without re-hitting YouTube's guarded transcript
endpoint, and are the substrate for richer briefings / timestamp deep-links.

## Scheduling (M/W/F)

Use the `cron-poll.sh` wrapper — it builds a PATH that finds `gws` (nvm node),
`yt-dlp`/`digest` (venv), and `node` under cron's minimal env:

```cron
# 7:30am Mon/Wed/Fri — poll: ingest, score, email the digest
30 7 * * 1,3,5 $HOME/ai-workspace/team-lib/integrations/ai-digest/cron-poll.sh >> ~/.config/ai-digest/poll.log 2>&1  # ai-digest MWF

# hourly at :15 — learn: one summary email per NEW video in the Summarize playlists
15 * * * * $HOME/ai-workspace/team-lib/integrations/ai-digest/cron-learn.sh >> ~/.config/ai-digest/learn.log 2>&1  # ai-digest LEARN hourly

# 11:00am Mon/Wed/Fri — primer: concept-level <=5 min read over recent transcripts.
# Runs AFTER the poll has landed its transcripts (fetches are paced ~10 min apart,
# so a 15-fetch poll can take ~2.5h). Reads only the on-disk store, so it makes no
# YouTube calls and adds ZERO block risk regardless of cadence. PRIMER_N overrides -n.
0 11 * * 1,3,5 $HOME/ai-workspace/team-lib/integrations/ai-digest/cron-primer.sh >> ~/.config/ai-digest/primer.log 2>&1  # ai-digest PRIMER MWF
```

Installed 2026-07-07. Recommended: add a `cookies_file` before relying on the
unattended cron over the full channel list (unauthenticated polls risk the IP
block; a blocked run aborts safely + cooldowns, but delivers no digest). Check
health any time with `digest doctor`.

## Rate-limit & block safety

YouTube blocks unauthenticated transcript access aggressively — by IP after too
many requests, and increasingly via PO-token enforcement. The tool defends on
three levels:

1. **Cookies (the durable fix).** Authenticated requests are treated far more
   leniently. Export a Netscape `cookies.txt` for youtube.com and set
   `youtube.cookies_file` — both the transcript API and the yt-dlp fallback use
   it (yt-dlp also uses `js_runtime = "node"` to mint PO tokens).

   > **How to get cookies.txt:** install the **"Get cookies.txt LOCALLY"**
   > extension (Chrome/Edge), open youtube.com while logged in, click the
   > extension → Export → save the file, then point `cookies_file` at it.
   > (On WSL, `cookies-from-browser` can't decrypt Windows Chrome's DPAPI cookies,
   > so the exported file is the reliable path.)

2. **Two-stage ingestion** (see *How it works*) — the transcript endpoint is only
   hit for a small, title-vetted shortlist, never once-per-new-video.

3. **Rate caps (proactive).** The transcript endpoint soft-blocks an IP around
   **~100-200 requests/hour** (empirical; no published limit). We stay far under
   with a **rolling-hour cap** (`max_transcripts_per_hour`, 30) + a 24h backstop
   (120) + **steady spacing** (`transcript_min_interval_sec`, 20s +jitter) — all
   persisted across invocations, so repeated runs can't burst into a block. When
   the budget is spent, transcripts **defer** to the next poll (fine at M/W/F).
   `digest doctor` shows `N/30 last hour · N/120 last 24h`.

4. **Abort-on-block (reactive).** The first block immediately stops the whole poll
   instead of hammering every remaining video.

5. **Cooldown.** After a block the tool records a `cooldown_hours` window and
   refuses to poll until it lapses (`--force` overrides; a success clears it).

Plus `request_delay_sec`/`channel_delay_sec` spacing **with jitter**. Relevance
and budget are separate: the title filter marks only *off-topic* items seen;
relevant-but-over-budget items are **deferred** (reconsidered next poll), never
silently dropped. Normal M/W/F load stays well under the caps even without
cookies — but cookies make it bulletproof.

## Notes / learnings

- **YouTube RSS (`feeds/videos.xml`) is dead from server hosts** — returns 404
  even for verified channel IDs. yt-dlp flat-playlist extraction is the robust
  substitute and doubles as the transcript fallback. (Verified 2026-06-29.)
- **Gemini free tier:** use `gemini-2.5-flash` (JSON response mode works);
  `gemini-2.0-flash` 429s on free quota. Scoring has 429/5xx backoff built in.
- Transcripts are English auto-captions via `youtube-transcript-api`; videos
  without captions are logged and skipped (never fatal).

## Roadmap

| Phase | Source | Status |
|-------|--------|--------|
| 1 | YouTube | ✅ built 2026-06-29 |
| 2 | Provider blogs (RSS/Atom — Anthropic, OpenAI, DeepMind…) | adapter TODO |
| 3 | Medium (per-author / per-tag RSS) | adapter TODO |
| 4 | X / Twitter (Apify; thread reconstruction; stricter gate) | adapter TODO |

See `../../../my-lib/backlog/260420-ai-content-digest.md` for the full design.
