# deals — marketplace deal-mining CLI

Find the best deal in **X** with objective criteria **Y**. `deals` scrapes a used
marketplace into a normalized **local CSV catalog**; once the data is local, all
the slow/expensive analysis (valuation, ranking, vision) runs fast and offline on
top of it.

The scrape layer is **pure and domain-agnostic** — it never knows whether you're
hunting gaming PCs, cameras, or guitars. Domain attribute schemas and valuation
are layered on downstream. OfferUp is the first marketplace adapter; the adapter
seam is built so eBay / Facebook Marketplace / Craigslist / Mercari slot in later
with zero change to the catalog or the analysis tools.

> Read/analysis tooling only. It never messages sellers or makes offers.

## Install

```bash
pip install -e ./consumer-deals          # or, for an isolated global tool: pipx install ./consumer-deals
```

Pure-stdlib core (Python 3.9+). The optional `browser` extra (Playwright) is only
a fallback for adapters that need a real captured session — OfferUp does not.

## Quick start

```bash
deals init                                  # one-time: scaffold ~/.config/deals/config.toml
deals scrape --query "gaming pc"            # feed sweep -> detail -> filters -> CSV
deals ls --under 500 --drops --sort drop    # quick filtered view
deals ls --since 2mo --sort distance
deals export --out gaming-pcs.csv           # hand the catalog to your analysis layer
deals diff --drops                          # rerun: what dropped in price since last scrape?
```

> `deals diff` is the detection primitive under automated deal-watching — see
> `DIFF_SPEC.md`. Domain attribute extraction + valuation are defined in
> `PACK_SPEC.md` (generated per-domain by a skill, not hand-coded).

## How it works (and why two stages)

OfferUp's cheap **search feed** only reliably exposes `listing_id / title / price /
location`. Everything else in the catalog — **price drops** (`previous_price`),
`posted_at`, `condition`, `is_firm` — is **detail-only** (one request per listing).
So a real catalog is built in two stages:

1. **Feed sweep** — paginate the search feed across your query(ies), dedup by id.
   Cheap; lets you pre-filter on a price band before paying for details.
2. **Detail pass** — fetch each survivor to complete the record (concurrent,
   resumable, fast: thousands of details in a few minutes).

`scrape` does both by default. `--fast` stops after stage 1 (a quick count; no
radius/age/price-drop, since those fields are detail-only).

### Price drops are first-class
OfferUp marks reduced listings with a struck-through previous price. `deals`
captures `previous_price`, `price_drop_amount`, and `price_drop_pct` — a strong
motivated-seller signal. (~1 in 3 live listings currently show a drop.)

### Rate-limit resilience (built in)
Detail fetching is the request-heavy step, so it's defended on three fronts:
- **Persistent cache** — every fetched detail is cached (`~/.config/deals/cache/`,
  24h TTL). Re-runs and analysis iterations reuse it (a second identical scrape is
  ~instant, zero API calls), and a throttled run **resumes from the cache** instead
  of refetching. `--refresh` re-fetches; `--no-cache` bypasses it.
- **Throttle + backoff** — requests are trickled (default 3/sec, `--rps`) at low
  concurrency (default 3), with exponential backoff + jitter on 403/429.
- **Circuit breaker** — on a run of throttle signals it stops early, writes the
  partial (cached) results, and tells you to resume later — instead of hammering a
  blocking endpoint.

### Filters (config-defaulted, per-command overridable)
- **Radius** — the marketplace's `radius` isn't enforced on deep pages, so `deals`
  post-filters on a per-listing distance localized to *your* configured location.
- **Age** — drop listings older than e.g. `2mo`.

## Configuration

All defaults live in `~/.config/deals/config.toml` (scaffolded by `deals init`),
never in the source. Override `DEALS_CONFIG_DIR` to relocate it.

```toml
[location]
zip = "92124"
lat = 32.82
lon = -117.10
name = "San Diego, CA"

[defaults]
radius_mi = 40
max_age   = "2mo"
site      = "offerup"
```

`deals init` resolves your ZIP → lat/lon (via Zippopotam.us; or pass `--lat/--lon`).

## Commands

| Command | What it does |
|---|---|
| `deals init` | Scaffold the central config (prompts for location/radius/age). |
| `deals refresh-auth --site offerup` | (Re)provision the site's device token. |
| `deals scrape --query Q [...]` | Feed sweep → detail → filters → CSV catalog. |
| `deals export [--format csv] [--out F]` | Re-emit the latest (or `--in`) catalog. |
| `deals ls [--under N] [--over N] [--since 2mo] [--drops] [--sort price\|drop\|distance] [--limit N]` | Quick filtered view. |
| `deals diff [OLD NEW] [--new-only] [--drops] [--gone] [--min-drop N] [--out delta.csv] [--exit-on-change]` | Rerun delta: new / gone / price changes vs a prior catalog (auto-picks the latest two). |
| `deals cache [--site offerup] [--clear]` | Inspect or clear the per-listing detail cache. |
| `deals value --pack <domain> [--in c.csv] [--out v.csv]` | Extract attributes + estimate value + score a catalog with a domain pack. |

`scrape` flags: `--query/-q` (repeatable), `--queries-file`, `--location`,
`--radius`, `--max-age`, `--max-price`/`--min-price` (cheap pre-filter), `--enrich`
(keep full description), `--fast` (feed only), `--max-pages`, `--concurrency`,
`--out`.

## Catalog schema

One CSV row per listing. **Core** is always filled; later tiers are null until you
opt in. Columns: `listing_id, site, url, title, price, currency, previous_price,
price_drop_amount, price_drop_pct, price_dropped, location_name, distance_mi,
posted_at, condition, is_firm, seller_id, image_urls, query_matched, first_seen,
last_seen` · *(Detail)* `description` · *(Vision)* `image_text` · *(Value)*
`attributes, est_value_min/avg/max, deal_score, flags` · `raw_json` (untouched
payload — no data is ever lost).

## Valuation (domain packs)

`deals value --pack <domain>` turns a raw catalog into ranked deals: it gates to
the domain, extracts attributes (regex over title/description/image_text), estimates
value from the pack's tables, and scores `deal_score = (value − price) / value`.

Packs are **config/data, not code** — a generic engine consumes any pack, so adding
a domain never touches the CLI. A pack lives in `~/.config/deals/packs/<domain>/`
(`pack.toml` + `value.csv`); a reference `gaming-pc` pack ships in `packs/`. Generate
or recalibrate one for any domain with the **`generate-deals-pack` skill** (team-lib),
which scrapes one cached sample then tunes the pack offline — so it never hits rate
limits. See `PACK_SPEC.md`.

> **Verify-not-verdict (hard rule):** a too-good-to-be-true score is flagged
> `verify_tier` (high-reward / high-verify), **never an auto-"scam" drop** — the
> underpriced outliers are the whole point. The engine quantifies the deal as-if-real
> and never silently excludes; it tempers with seller tenure (`seller_id`).

## Roadmap
- `--vision` — OCR spec sheets in photos (decisive specs often live only there).
- SQLite store — recurring searches, price-history-over-time, incremental scrape.
- More marketplace adapters (eBay, FB Marketplace, Craigslist, Mercari).

## License

MIT.
