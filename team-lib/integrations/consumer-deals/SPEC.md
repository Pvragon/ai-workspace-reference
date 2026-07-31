---
template: cli-design-spec
version: 0.2.0
summary: Design spec for `deals` — a marketplace deal-mining CLI (OfferUp adapter first). Scrapes listings → normalized catalog → CSV; downstream enrich/value/score layers on top. Build steps 1–4 SHIPPED 2026-06-22.
created: 2026-06-22
last_updated: 2026-06-22
maintainer: your-agent / the-operator
status: build-in-progress (steps 1-4 done; value/vision/sqlite pending)
---

# `deals` CLI — Design Spec

## ⚙️ Build status (2026-06-22)
Steps 1–4 of "Build order" are **shipped and live-verified** (24 unit tests pass;
end-to-end scrape→ls→export run against the real API). Empirical corrections to
this spec from build-order step 1 (full record: `runtime/.tmp/260622-deals-cli-probe/FINDINGS.md`):
- **Price drop = `originalPrice` (detail) + `priceDropPercentage` (detail).** Drop iff
  `originalPrice > price`. Both **detail-only** — the search tile carries them but unpopulated.
- **Feed arg is `modularFeed(params: [SearchParam])`**, not `searchParams` (memory was wrong).
- **Core is detail-only.** The cheap tile gives only id/title/price/location/flags; `posted_at`,
  `condition`, `is_firm`, price-drop all require the per-listing detail fetch → census is **two-stage**,
  and `scrape` is **detail-by-default** (`--fast` = feed-only quick count). [decision locked w/ the operator]
- **Geo without a zip DB:** detail `distance{value,unit}` localized via an unsigned `userdata` JWT built
  from config lat/lon; radius filter = `distance.value <= radius`. Only init geocodes the user's own zip.
- **Auth is trivial:** device token is not validated → `refresh-auth` mints `web-<56hex>` locally; no Playwright.

## Purpose & generalized use case

> "Find the best deal in **X** with objective criteria **Y**."

Proven by hand on a San Diego gaming-PC hunt (see `my-lib/runtime/.tmp/260620-offerup-gaming-pc-deal-mine/` and memory `project_offerup-deal-mining-skill`). This CLI productizes the **stable, reusable** half of that pipeline.

The pattern: **scrape all listings → catalog attributes → estimate value independently → compare to list price.** This tool owns the parts that are deterministic and marketplace-specific; domain attribute schemas and valuation are *fed in*, not baked into the CLI.

## Architecture — where the seam falls

| Pattern step | Nature | Owner |
|---|---|---|
| Scrape all listings | deterministic, marketplace-specific, domain-agnostic | **CLI core (stable) — adapter** |
| Catalog attributes | generic normalize + domain extract | CLI normalizes; domain extractor (regex+LLM) plugs in |
| Estimate value | judgment, domain-specific | downstream `value` step (tables + LLM) |
| Compare → rank | deterministic, generic | CLI generic scorer |

**The CLI stays ignorant of what's being sold.** Domain knowledge = config/data, not code. This is the 3-layer architecture: CLI = Layer 3 (executions), per-domain valuation = config, hunt orchestration = Layer 2 (the agent) per a Layer 1 directive.

### Adapter seam
OfferUp is **adapter #1**. All marketplace logic sits behind an adapter interface that emits the normalized record below. eBay / FB Marketplace / Craigslist / Mercari become additional adapters later with zero change to downstream consumers. Build the interface now even though only OfferUp is implemented.

## The scrape contract (normalized record, tiered)

| Tier | Fields | Filled by |
|---|---|---|
| **Core** (always) | `listing_id` · `site` · `url` · `title` · `price` · `currency` · **`previous_price` · `price_drop_amount` · `price_drop_pct` · `price_dropped`** · `location_name` · `distance_mi` · `posted_at` · `condition` · `is_firm` · `seller_id` · `image_urls[]` · `query_matched` · `first_seen` · `last_seen` · `raw_json` | scrape |
| **Detail** (`--enrich`) | `description` (full body text) | per-listing fetch |
| **Vision** (`--vision`, opt-in) | `image_text` (OCR of spec sheets/labels + caption of what's pictured & condition) | vision model per image |
| **Value** (`--value <domain>`, opt-in) | `attributes{}` · `est_value_min/avg/max` · `deal_score` · `flags{}` | domain extractor + valuation |

Notes:
- **Text:** `title`, `description` (the catalog text), and `raw_json` (untouched payload — never lose data).
- **Price reductions** are a Core raw fact (OfferUp shows a struck-through previous price). Strong motivated-seller signal → first-class fields. *First build task: locate the API field (probe `modularListing` fragment + detail `listing` for `originalPrice` / `wasPrice` / `priceDropInfo` / `discount`, same error-probe technique used to map the detail query).*
- **Image→text** is high-value, not cosmetic: decisive attributes routinely live only in photos (e.g. the iBuyPower spec sheet). Domain-agnostic. Opt-in (per-image cost); run on the **candidate funnel**, not the full census.
- **Valuation** fields are reserved but null until the opt-in `value` step runs — keeps scrape pure and re-valuable without re-scraping.

## Config — central user config, NO defaults in code

- All defaults live in a **central user config file** (e.g. `~/.config/deals/config.toml`), never hardcoded.
- `deals init` scaffolds the config (prompts for location/radius/max-age) on first run.
- Config holds: default `location` (ZIP), `radius_mi`, `max_age` (e.g. `2mo`), output prefs, auth file path.
- Reference defaults for the primary user: **ZIP 92124 · 40 mi · 2 months** — but these go in *their* config, not the source.

## Post-filters (config-defaulted, CLI-overridable)
- **Radius:** OfferUp's `radius` param is NOT enforced on deep pagination (feed is distance-ranked, not limited) → **always post-filter by haversine** from the configured location. Default 40 mi.
- **Listing age:** post-filter on `posted_at`. Default **2 months**. Same override pattern as radius.

## CLI command surface (v1)
```
deals init                         # scaffold central user config
deals refresh-auth --site offerup  # one-time headless capture of THIS user's session headers
deals scrape --site offerup --query "gaming pc" [--location 92124] [--radius 40] [--max-age 2mo] [--enrich] [--queries-file q.txt]
deals export --format csv [--out file.csv]
deals ls [--since 2mo] [--under 700] [--site offerup]   # quick filtered view
```
- `scrape` runs the multi-query census, dedups by `listing_id`, applies radius+age post-filters, writes the catalog (CSV for now).
- `--enrich` adds the per-listing description fetch (concurrent, resumable).
- Vision (`--vision`) and value (`--value`) are later milestones (separate subcommands or flags).

## Auth design ("anyone can use it")
- **No personal tokens in the repo, ever.** `refresh-auth` drives a one-time headless Playwright run, navigates an OfferUp search, captures the live request headers (`x-ou-d-token`, `ou-session-id`, `userdata` JWT, etc.), and stores them in `~/.config/deals/auth.json` (gitignored).
- The fast Python scraper reads those headers; on a 401 / empty-feed it **auto-triggers `refresh-auth` and retries**. Capture-once, reuse-many, self-heal. This is the #1 stability mechanism.

## Guardrails to encode (hard-won from the PoC)
Bake into the generic layer so every future hunt inherits them:
- **Radius not enforced on deep pages** → haversine post-filter (above).
- **Dealer / financing listings post fake teaser prices** (e.g. "$680" RTX 5070 Ti = $2,040 cash; Miramar Rd store, "no credit needed / $10 down") → detect & flag.
- **`is_firm` / broken ("has some issues", "needs diagnostic") / stale** → first-class flags; they change achievable price.
- **Spec mis-extraction from "upgrade to / compatible with / enough power for" phrasing** → context-aware extraction (prefer title; skip upgrade-context mentions).

## OfferUp adapter specifics (from PoC — see memory `reference_offerup-scraping-graphql`)
- Endpoint: `POST https://offerup.com/api/graphql` (Apollo; **no cookies needed** with static device headers; plain `urllib`/httpx works).
- **Search = `GetModularFeed`**: full query sent inline (persisted-query hash NOT enforced → send a minimal field selection). `searchParams` = `{q, platform=web, zipcode, radius, experiment_id=experimentmodel24, page_cursor, limit=50, searchSessionId}`. Response: `looseTiles[]` + `modules[].grid.tiles[]` (`ModularFeedTileListing`), plus `pageCursor`. Loop until tiles empty / cursor repeats. 100% coverage = multi-query sweep, dedup by `listingId`.
- **Detail = `listing(listingId: ID!)`**: introspection disabled → probe field errors to discover names. Confirmed-good: `listingId title price description conditionText isFirmOnPrice postDate`. `description` holds the spec text.
- Item URL = `https://offerup.com/item/detail/<listingId>`.

## Repo & conventions
- Home: **`team-lib/integrations/consumer-deals/`** (start in team-lib, graduate to standalone later).
- Follow the existing CLI conventions (the ClickUp CLI + restish-based integrations + `waystar-cli`): repo layout, central config location, auth handling, README/usage.
- Build clean & shareable: `pipx`-installable, license, README, a couple of tests. Command name `deals`.

## Build order (next session)
1. **Probe the price-drop API field** (Core contract depends on it) + confirm minimal feed/detail queries.
2. Adapter interface + OfferUp adapter (`refresh-auth`, `scrape`, `--enrich`).
3. Central config (`init`) + post-filters (haversine, age).
4. CSV catalog + `export` / `ls`.
5. (Later) domain extractor, `--vision`, `--value`, SQLite store for recurring searches.

## Deferred / future
- SQLite store → recurring searches, price-history-over-time, incremental scrape (user confirmed wanted later).
- Additional marketplace adapters.
- Domain valuation packs (gaming-PC pack is the first; web-calibrated component tables).
