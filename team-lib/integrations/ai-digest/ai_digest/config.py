"""Central user config for ai-digest.

Mirrors the consumer-deals philosophy: the source ships only the config *schema* and
a seed template; all operational values live in the user's scaffolded config
file. ``digest init`` writes the template (including the recommended starter
channel list) into the config dir, where the user edits freely.

Location: $AI_DIGEST_CONFIG_DIR or ~/.config/ai-digest/
  config.toml   — channels + scoring/digest settings (this module)
  corpus.db     — SQLite dedupe + rolling-corpus store (ai_digest.corpus)
  digests/      — rendered digest text, one file per poll (audit trail)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

try:                        # py311+
    import tomllib as _toml
except ModuleNotFoundError:  # py<=310
    import tomli as _toml    # type: ignore


# --- paths -----------------------------------------------------------------
def config_dir() -> Path:
    d = os.environ.get("AI_DIGEST_CONFIG_DIR")
    return Path(d).expanduser() if d else Path.home() / ".config" / "ai-digest"


def config_path() -> Path:
    return config_dir() / "config.toml"


def corpus_path() -> Path:
    return config_dir() / "corpus.db"


def digests_dir() -> Path:
    return config_dir() / "digests"


def transcripts_dir() -> Path:
    return config_dir() / "transcripts"


# --- secrets ---------------------------------------------------------------
SECRETS_ENV = Path.home() / "ai-workspace" / "personal" / "secrets" / ".env"


def load_secret(name: str) -> str | None:
    """Read a single KEY from the workspace .env. Never logs the value."""
    if os.environ.get(name):
        return os.environ[name]
    if not SECRETS_ENV.exists():
        return None
    for ln in SECRETS_ENV.read_text().splitlines():
        m = re.match(r'\s*([A-Z_0-9]+)\s*=\s*"?([^"\n]*)"?', ln)
        if m and m.group(1) == name:
            return m.group(2)
    return None


# --- load ------------------------------------------------------------------
def resolve_gemini_key(conf: dict) -> tuple:
    """(api_key, source_env_name). Prefer the configured (billing) key, then the
    billing key, then the free key. Returns (None, tried) if none are set."""
    tried = []
    configured = (conf.get("scoring", {}) or {}).get("gemini_api_key_env")
    for name in [configured, "GEMINI_AGENTIC_MEDIA_API_KEY", "GEMINI_FREE_API_KEY"]:
        if not name or name in tried:
            continue
        tried.append(name)
        k = load_secret(name)
        if k:
            return k, name
    return None, tried[-1] if tried else "GEMINI_FREE_API_KEY"


def load() -> dict[str, Any]:
    p = config_path()
    if not p.exists():
        raise FileNotFoundError(
            f"No config at {p}. Run `digest init` to scaffold it."
        )
    return _toml.loads(p.read_text())


# --- scaffold --------------------------------------------------------------
# Recommended starter channels. yt-dlp validates each handle at poll time;
# any that fail to resolve are logged and skipped, never crash the run.
# Curated for APPLIED AI + AI-business methodology (per the operator's 2026-06-30
# directive: usable findings, not pure research). Pure-research channels
# (Two Minute Papers, Yannic Kilcher, etc.) are intentionally excluded. Handles
# that no longer resolve are logged + skipped at poll time — safe to leave in.
SEED_CHANNELS = [
    # --- agentic dev / practitioners ---
    ("IndyDevDan",       "@indydevdan"),
    ("Cole Medin",       "@ColeMedin"),
    ("AI Jason",         "@AIJasonZ"),
    ("Matthew Berman",   "@matthew_berman"),
    ("Sam Witteveen",    "@samwitteveenai"),
    ("AI Explained",     "@aiexplained-official"),
    ("David Ondrej",     "@DavidOndrej"),
    ("Prompt Engineering", "@engineerprompt"),
    ("Nicholas Renotte", "@NicholasRenotte"),
    ("Riley Brown",      "@rileybrownai"),
    # --- labs / tooling (official) ---
    ("Anthropic",        "@anthropic-ai"),
    ("OpenAI",           "@OpenAI"),
    ("Google DeepMind",  "@GoogleDeepMind"),
    ("LangChain",        "@LangChain"),
    # --- news / analysis (applied, tool-focused) ---
    ("Matt Wolfe",       "@mreflow"),
    ("Wes Roth",         "@WesRoth"),
    # --- conferences / deep dives ---
    ("Latent Space",     "@LatentSpaceTV"),
    ("AI Engineer",      "@aiDotEngineer"),
    # --- AI business & product methodology ---
    ("Greg Isenberg",    "@GregIsenberg"),
    ("Lenny's Podcast",  "@LennysPodcast"),
    ("My First Million", "@MyFirstMillionPod"),
    ("Y Combinator",     "@ycombinator"),
    ("a16z",             "@a16z"),
    # --- added from the operator's subscriptions 2026-07-07 (AI + business filtered) ---
    ("Nate B Jones · AI Strategy", "@NateBJones"),
    ("AI Edge",          "@AIEdgeHQ"),
    ("Alex Finn",        "@AlexFinnOfficial"),
    ("Nick Saraev",      "@nicksaraev"),
    ("Nate Herk · AI Automation", "@nateherk"),
    ("Dylan Davis",      "@dylandavisAI"),
    ("Eric Tech",        "@EricWTech"),
    ("Rob Shocks",       "@RobShocks"),
    ("Agentic Lab",      "@AgenticLab1"),
    ("Kyle Friel · AI Software", "@KyleFrielTech"),
    ("Michele Torti · AI Automation", "@michtortiyt"),
    ("Discover AI",      "@code4AI"),
    ("Google Antigravity", "@googleantigravity"),
    ("Chris Koerner",    "@thekoerneroffice"),
    ("SaaS Academy",     "@SaaSAcademy"),
    ("NetworkChuck",     "@NetworkChuck"),
]

_HEADER = """\
# ai-digest — user config. Edit freely.
# Scaffolded by `digest init`. Channels are validated at poll time; a handle
# that no longer resolves is logged and skipped (the run never crashes on it).

[scoring]
model            = "gemini-2.5-flash"  # JSON response mode
# Which .env key to use. The billing-enabled key avoids free-tier 429s; costs a
# rounding error for flash text (<1c/poll). Falls back to GEMINI_FREE_API_KEY.
gemini_api_key_env = "GEMINI_AGENTIC_MEDIA_API_KEY"
threshold        = 8                   # 0-10; items scoring >= threshold pass (8 = strict gate)
# Two-stage ingestion (never trip YouTube's transcript IP-guard):
#   1. scan ALL channels for new titles (cheap listing, safe endpoint)
#   2. LLM downselects on title, then transcripts are fetched ONLY for the
#      vetted shortlist, hard-capped at max_transcripts_per_poll.
scan_per_channel      = 8              # new titles scanned per channel (cheap pass)
# Transcript endpoint soft-blocks an IP around ~100-200 req/hour (empirical). We
# stay far under with a rolling-hour cap + steady spacing; overflow DEFERS to the
# next poll (fine at M/W/F cadence). See README "Rate-limit & block safety".
max_transcripts_per_poll = 15          # cap per single poll
max_transcripts_per_hour = 30          # rolling-60min cap across ALL runs (primary limiter)
max_transcripts_per_day  = 120         # rolling-24h backstop
transcript_min_interval_sec = 20       # steady spacing between transcript fetches (+jitter)
enrich_multiple       = 2              # page-GET descriptions for up to budget*this candidates
transcript_max_chars = 24000           # truncate long transcripts before scoring
corpus_context_n = 40                  # recent digested items fed to the judge
novelty_reserve  = 5                   # transcript slots reserved for NON-interest items so a
                                       # big ★-interest backlog can't starve pure-novelty finds
interest_floor   = 6                   # a ★-interest item earns a "For you" spot only if its
                                       # TRANSCRIPT scores >= this (marketing/thin ones drop out)
persist_transcripts = true             # keep raw transcripts on disk (config/transcripts/, one JSON
                                       # per video) so digests can be re-synthesized without re-fetching

# Throttling — YouTube 429-blocks an IP that fetches transcripts too fast.
# These delays keep polite spacing; defaults are safe for the M/W/F cadence.
request_delay_sec = 4.0                # sleep between per-video transcript fetches (+jitter)
channel_delay_sec = 4.0               # extra sleep between channels (+jitter)
max_total_items   = 40                 # hard cap on items fetched per poll (all channels)
cooldown_hours    = 12                 # after a YouTube block, skip polling this long

[recency]
# Only items published since the last poll, but never a window shorter than
# min_window_hours (so back-to-back runs still look back a full day). First run
# (or a newly-added channel) uses initial_window_hours.
min_window_hours     = 24
initial_window_hours = 24

[digest]
recipient = "you@example.com"
cadence   = "M/W/F"                     # informational; cron drives real timing

[brief]
# The hero of the email: one synthesized article woven from ALL the chosen
# transcripts (theme-organized), so you learn the material without watching. It
# is published as a Google Doc (via gws — never MCP) and linked at the top of the
# email. Set enabled=false to skip. "dense" (max learning-per-word) is the ONLY
# style — the "verbose" prose style was retired 2026-07-29.
enabled = true
styles  = ["dense"]

[interests]
# Personal-interest signals — an ADDITIVE, separate axis from novelty. Items whose
# title/description matches ANY topic below are:
#   • NEVER dropped as off-topic by the relevance/description gates,
#   • exempt from the recency window (they surface even if not brand-new),
#   • prioritized for the transcript budget, and
#   • shown in a dedicated "★ For you" digest section (SEPARATE from the novelty
#     "Worth your time" list, so novelty scoring stays clean and you see WHY it's there).
# Remove a topic and its videos stop appearing. To let an already-seen video
# resurface after adding a topic, run `digest forget <keyword>` (or `digest reset
# --seen` for a full one-time re-consideration of history).
topics = [
  "Using AI agents to GENERATE MONEY via agentic go-to-market — including agentically producing marketing/content VIDEOS (e.g. making videos with Claude Code), agentic content pipelines, and AI-run distribution.",
  "Fully AGENTIC MICRO-PRODUCT creation and selling — agents as end-to-end revenue engines that build and sell a small product with minimal human involvement.",
  "NEW PATTERNS of advanced agentic engineering — reusable techniques or tools that, added to an agent's toolkit, make it materially more powerful (e.g. the Ralph Loop, multi-agent orchestration like IndyDevDan's CMUX), agent self-improvement patterns, and second-brain / knowledge systems for agents.",
]

"""


_YOUTUBE_HEADER = """\
[youtube]
# Cookies AUTHENTICATE transcript requests and are the durable fix for persistent
# IP / PO-token blocks. Export a Netscape cookies.txt for youtube.com (e.g. the
# "Get cookies.txt LOCALLY" browser extension) and point cookies_file at it.
cookies_file         = ""      # path to a youtube.com cookies.txt (recommended)
cookies_from_browser = ""      # yt-dlp browser name e.g. "chrome" (unreliable on WSL/DPAPI)
js_runtime           = "node"  # lets yt-dlp mint PO tokens; "" to disable

"""


_LEARN_HEADER = """\

# --- `digest learn` — playlist "learnings" mode ----------------------------
# Summarize each NEW video added to a curated (unlisted) playlist: one concise,
# information-dense learnings email per video, so you get the value without
# watching. NO filtering — you curated it by adding it. Topic-agnostic (AI,
# health, whatever). Reuses the shared transcript rate-limiter + cookies +
# cooldown, so it can never collide with the news digest and trip the guard.
# Add/remove playlists freely. `digest learn` lists each, diffs against the
# seen-set, and summarizes only the new ones.
# `subject_tag` is stamped into every learn subject line so the summaries are
# reliably searchable in Gmail. Search it as a QUOTED PHRASE:
#     subject:"AI Summary"
# Bare `subject:summary` is useless (301 hits in this mailbox). Do NOT rely on
# the 📝 emoji either — Gmail strips emoji from queries, so `subject:📝` matches
# the entire mailbox. Before changing this value, verify the new phrase returns
# 0 hits. Set to "" to omit the tag.
[learn]
recipient            = "you@example.com"
subject_tag          = "AI Summary:"
summary_min_words    = 200
summary_max_words    = 500
transcript_max_chars = 200000   # feed the FULL transcript (Gemini 1M-token window) — don't truncate learnings
max_per_run          = 10       # cap new videos summarized per run (shares the hourly transcript budget)

# --- `digest primer` — concept-level rapid primer ---------------------------
# Changes the unit of analysis from the VIDEO to the IDEA. Concepts are extracted
# per transcript, clustered across videos, matched against a persistent ledger,
# then ranked. Two independent routes to the top:
#   CONVERGING — many independent creators said it; the trend is confirmed, but
#                you are hearing it after it spread.
#   EARLY      — one high-authority creator said it FIRST. Unconfirmed, and the
#                most valuable thing in the feed when it is right.
# `trusted_sources` bootstraps the second route: prescience is EARNED from the
# ledger (of the ideas you raised first, how many did others later pick up?), but
# it reads 0 for everyone until enough history accrues. List the creators whose
# solo signal you already trust; remove them once the ledger has an opinion.
[primer]
enabled        = true
recipient      = "you@example.com"
max_words      = 1000   # HARD cap, enforced in code — ~5 min at 220 wpm
n_headlines    = 8      # one-line scannable items ("what changed")
n_dives        = 4      # concepts that get ~90 words of explanation
converge_at    = 3      # distinct producers before an idea counts as CONVERGING
min_firsts     = 3      # first-raises needed before prescience is trusted at all
trusted_sources = [
  "IndyDevDan",
  "Latent Space",
  "Nate B Jones · AI Strategy",
  "AI Explained",
]
# Ranking weights. `pioneer` is what lets a single trusted creator outrank a
# crowd; drop it to 0 to score purely on convergence.
[primer.weights]
sources  = 1.0
new      = 2.5
velocity = 1.5
impact   = 2.0
pioneer  = 3.0

[[learn.playlists]]
name = "Personal"
url  = "https://www.youtube.com/playlist?list=PLZzczkHHKXd0"

[[learn.playlists]]
name = "Work"
url  = "https://www.youtube.com/playlist?list=PLZPZ1rn6yWr8"
"""


def render_template() -> str:
    lines = [_HEADER, _YOUTUBE_HEADER, "# --- YouTube channels (Phase 1) ---"]
    for name, handle in SEED_CHANNELS:
        lines.append("[[youtube.channels]]")
        lines.append(f'name   = "{name}"')
        lines.append(f'handle = "{handle}"')
        lines.append("")
    lines.append(_LEARN_HEADER)
    return "\n".join(lines)


def init(force: bool = False) -> Path:
    config_dir().mkdir(parents=True, exist_ok=True)
    digests_dir().mkdir(parents=True, exist_ok=True)
    p = config_path()
    if p.exists() and not force:
        return p
    p.write_text(render_template())
    return p
