---
template: integration-doc
version: 1.3.0
summary: Agent-facing reference for the `deals` CLI — marketplace deal-mining (OfferUp adapter). How to scrape a normalized local catalog, the two-stage scrape model, the OfferUp GraphQL mechanics, and the adapter seam.
created: 2026-06-22
last_updated: 2026-06-22
maintainer: your-agent
status: active
---

# consumer-deals — Integration Notes

`deals` productizes the stable half of the OfferUp deal-mining pipeline
(`project_offerup-deal-mining-skill`): **scrape all listings → normalized local
catalog (CSV)**. Valuation/ranking/vision are downstream, opt-in layers — the
scrape layer is pure and domain-agnostic.

## When to use (Layer 3 execution)
Use this CLI whenever a hunt needs "find the best deal in X with criteria Y" and
step one is *get every candidate listing into a spreadsheet*. The agent
(Layer 2) drives queries/filters per a directive (Layer 1); `deals` owns the
deterministic scrape + catalog.

## Install / invoke
- `pipx install ./consumer-deals` (command `deals`), or run in-tree: `python3 -m deals …`
- Config dir: `$DEALS_CONFIG_DIR` or `~/.config/deals/`. For throwaway/test runs,
  set `DEALS_CONFIG_DIR` to a `.tmp` path so nothing touches the user's real config.

## Command recipes
```bash
deals init --zip 92124 --radius 40 --max-age 2mo --site offerup --yes   # non-interactive scaffold
deals scrape --query "gaming pc" --max-price 700 --enrich                # full Core + description
deals scrape -q "gaming pc" -q "custom pc" --queries-file extra.txt      # multi-query sweep (dedup by id)
deals scrape --query "gaming pc" --fast --max-pages 3                    # quick count, feed-only
deals ls --under 500 --drops --sort drop          # cheapest price-drops first
deals export --out catalog.csv                    # hand off to the valuation layer
deals diff OLD.csv NEW.csv --drops --out delta.csv  # rerun delta: new/gone/price changes
deals diff --exit-on-change                        # exit 10 if new/dropped (cron-friendly)
```
All scripts/commands are chainable; the catalog CSV is the hand-off artifact.

## Rerun diff (`deals diff`) — the watch primitive
Keys by `listing_id`; classifies `new` / `gone` / `price_drop` / `price_rise` /
`unchanged`. `gone` ≠ sold (could be delisted/expired/out-of-window — labeled
honestly). Catches **price changes between runs** even when OfferUp shows no
strike-through — the motivated-seller signal. No args → auto-diffs the two most
recent catalogs in `catalogs_dir`. `--exit-on-change` returns exit code 10 so a
scheduler can branch. Full design + the path to automated deal-watching (incremental
newest-first poll + price/gone re-scan + alert sink, read-only) in `DIFF_SPEC.md`.

## Rate-limit resilience (deals/cache.py + deals/throttle.py)
Detail is the request-heavy endpoint and the one that gets throttled. Defenses:
- **Persistent detail cache** (`<config>/cache/<site>/<id>.json`, 24h TTL): re-runs
  and skill iterations are free; a throttled run **resumes from cache**. `--refresh`
  re-fetches, `--no-cache` bypasses, `deals cache [--clear]` manages it.
- **RateLimiter** (default 3 rps, `--rps`) + low concurrency (default 3) + backoff
  with jitter on 403/429/503.
- **CircuitBreaker**: trips after a run of throttle signals (HTTP 403/429 or
  ≥12 consecutive empty details) → `fill_details` stops early, sets
  `adapter.last_throttled`, returns partials (cached). The CLI warns and the
  partial catalog is written. **Never fan out parallel live scrapers** — that
  thundering herd is what caused the original block; scrape once, share the cache.

## Domain packs + `deals value` (deals/packs.py) — BUILT
Attribute extraction + valuation are **config/data, not code**: a per-domain *pack*
(`pack.toml` + `value.csv`) consumed by the generic `deals value --pack <domain>`
engine. The CLI never changes per domain. `apply_pack`: gate to in-domain (title-only
include/exclude — coarse, refined by the skill's LLM pass) → regex extract attributes
(skip aspirational "upgrade to" phrasing) → table value (requires ≥1 recognized
component; won't value a spec-less item off base alone) → `deal_score = (value−price)/
value` → `verify_tier` flag when too-good (NEVER a drop). Packs resolve from
`<config>/packs/<domain>` then the repo `packs/`; reference `gaming-pc` pack ships.
Out-of-domain listings are flagged, never dropped (catalog stays complete).

Generate/recalibrate packs with the **`generate-deals-pack`** skill (team-lib):
scrape ONE cached sample → research comps → draft pack → validate + converge OFFLINE
against the cache (zero further API calls) → stamp `calibrated_on`. Rate-limit-safe by
construction. See `PACK_SPEC.md`.

## Two-stage scrape (IMPORTANT)
OfferUp's search **tile** only fills `listing_id/title/price/location/flags`.
`previous_price`, `posted_at`, `condition`, `is_firm` are **detail-only**, and the
tile has no date field. So:
- **Default** (`scrape`): feed sweep → per-listing detail → full Core. Radius + age
  + price-drop filters apply (they need detail fields). `--enrich` also keeps the
  full `description`.
- **`--fast`**: stage-1 only. No radius/age/price-drop (those fields aren't on the
  tile). Use for a quick population count, not for analysis.

## OfferUp GraphQL mechanics (verified 2026-06-22; see consumer-deals FINDINGS + memory
## reference_offerup-scraping-graphql)
- Endpoint `POST https://offerup.com/api/graphql`. **Device token is NOT validated**
  (any/empty token works) → `refresh-auth` just mints `web-<56 hex>` locally; no
  cookies, no browser.
- **Search**: `modularFeed(params: [SearchParam])` — NOT `searchParams` (the PoC
  memory was wrong; corrected here). `params` = `{key,value}` list (q, platform=web,
  zipcode, radius, experiment_id=experimentmodel24, page_cursor, limit=50,
  searchSessionId). Header `ou-experiment-data: {"datamodel_id":"experimentmodel24"}`.
  Response: `looseTiles[]` + `modules[].grid.tiles[]` (`ModularFeedTileListing`),
  `pageCursor`. Paginate to exhaustion; dedup by `listingId`.
- **Detail**: `listing(listingId: ID!)`. Confirmed fields: `listingId title price
  originalPrice priceDropPercentage formattedPrice conditionText isFirmOnPrice
  postDate description distance{value unit}`. Introspection off → probe field
  errors to extend.
- **Price drop**: `originalPrice` = pre-drop price; drop iff `originalPrice > price`.
  `priceDropPercentage` (e.g. "21%") is populated only on genuine drops. Both
  detail-only.
- **Distance/geo**: no lat/lon on listings. `distance{value,unit}` is localized to
  the request's **`userdata` JWT** header — an *unsigned* (`alg:none`) JWT with
  payload `{"location":{zipCode,latitude,longitude}}`. Plain base64 is ignored.
  `deals` builds it from config lat/lon; radius filter = `distance.value <= radius`.

## Adapter seam
`deals/adapters/base.py:Adapter` — implement `feed_sweep` + `fill_details` (and get
`scrape` for free). Register in `deals/adapters/__init__.py`. Downstream
(catalog/filters/export/value) is adapter-agnostic. eBay/FB/Craigslist/Mercari are
future adapters; some will need real auth → store it in `auth.json` (per-site dict),
the self-heal-on-401 path is uniform.

## Guardrail flags (deals/flags.py)
Domain-agnostic signals computed on every detailed listing (`flags` column):
`dealer` (financing/teaser price), `broken` (for-parts/issues), `firm` (is_firm or
text). **They annotate; nothing here ever drops a listing.**

## Value-layer constraint (when step 5 / `--value` is built) — HARD
Per memory `feedback_deal-mining-scam-flag-is-verify-not-verdict`: a
too-good-to-be-true price (e.g. a $900 RTX 4090 system) is a **VERIFY-HARD /
high-reward signal, NEVER an auto-"scam" drop**. Desperate or clueless sellers
posting genuine steals are the entire target of this tool. The value layer must:
quantify the deal *as if real* (value range + deal_score + flip/keep upside),
surface it in a "high-reward, high-verify" tier with an in-person verification
checklist, and temper the flag with seller legitimacy signals (account
tenure — `seller_id`/`ownerId` is captured for exactly this). Never silently
exclude or hard-label "scam."

## Caveats
- `--fast` catalogs lack distance/age/price-drop — don't run analysis on them.
- The scrape is domain-blind: a "gaming pc" sweep also catches monitors, RAM, VR
  headsets. Domain filtering belongs to the downstream extractor/value layer.
- Listings with `price = 0` ("make offer") can produce odd drop percentages —
  handle in the valuation layer.
