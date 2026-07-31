---
template: cli-design-spec
version: 0.1.0
summary: Design spec for domain packs — the stable, declarative seam between the generic deals CLI and per-domain attribute extraction + valuation. Plus the generator skill that produces a pack for any new domain.
created: 2026-06-22
last_updated: 2026-06-22
maintainer: your-agent / the-operator
status: spec (pre-build — defines the contract before stages 5/7)
---

# Domain Packs + the pack-generator skill — Design Spec

## The core idea

Stages 5 (attribute extraction) and 7 (valuation) are **not code we rewrite per
hunt** — they are **config/data** the *generic* CLI consumes. A **domain pack** is
a self-contained, declarative bundle describing how to read and value listings in
one domain (gaming PCs, mountain bikes, DSLR lenses…). The CLI ships a single
generic extractor + scorer; the *knowledge* lives in packs. A **skill generates a
pack** for any new domain in minutes, so opening a new hunt is "generate a pack,"
not "write an extractor."

This is the 3-layer architecture exactly: CLI = Layer 3 (deterministic generic
engine), pack = config/data, generator skill = Layer 2 orchestration over a Layer 1
directive.

## Where packs live & how they're invoked

- Location: `~/.config/deals/packs/<domain>/` (user packs) and an optional
  repo-shipped `packs/` for sharing. Resolved by name.
- Invoked: `deals scrape --query "gaming pc" --value gaming-pc` (extract + value),
  or `deals value --pack gaming-pc --in catalog.csv` as a standalone pass over an
  existing catalog (keeps scrape pure & re-valuable without re-scraping).

## Pack anatomy

```
packs/gaming-pc/
  pack.toml        # metadata + attribute schema + scoring weights + provenance
  extract.toml     # regex pre-extractors, skip-phrases (guardrails), text sources
  prompt.md        # LLM extraction/normalization prompt (optional, for ambiguous)
  value.csv        # component/feature value table (feature -> min/avg/max)
  samples.csv      # the listings the pack was validated against (provenance)
```

### `pack.toml` — schema + scoring + provenance
```toml
[meta]
domain = "gaming-pc"
version = "1.0.0"
calibrated_on = "2026-06-22"     # value data is PERISHABLE — see below
perishable_after = "60d"          # warn/recalibrate past this
value_sources = ["https://…pcpartpicker…", "ebay-sold-comps", …]

[attributes]                      # what to extract; drives value
gpu   = { type = "string", drives_value = true, examples = ["RTX 4070", "RX 6700 XT"] }
cpu   = { type = "string", drives_value = true }
ram_gb = { type = "int" }
storage_gb = { type = "int" }
condition = { type = "enum", values = ["new","like-new","used","for-parts"] }

[scoring]                          # generic formula; pack supplies weights
# deal_score = (est_value_avg - effective_price) / est_value_avg, adjusted by flags
weight_condition = 0.8            # used/for-parts discounts achievable value
addons = { monitor = 80, kb_mouse = 25 }   # effective-cost normalization
```

### `extract.toml` — deterministic first, LLM fallback
```toml
text_sources = ["title", "description", "image_text"]   # in priority order
[regex]                            # cheap, offline pre-extraction
gpu = '\b(rtx|gtx|rx)\s?\d{3,4}\s?(ti|super|xt)?\b'
ram_gb = '(\d{1,3})\s?gb\s?(ddr\d)?\s?ram'
[guardrails]                       # hard-won: don't mis-extract
skip_phrases = ["upgrade to", "compatible with", "supports", "enough power for"]
prefer_source = "title"            # title beats body for the headline part
```

### `value.csv` — the valuation model
A feature → value-range table (the half that goes stale), e.g.:
```
feature,key,min,avg,max
gpu,RTX 4070,420,500,560
gpu,RTX 3060,180,230,270
cpu,i7-12700K,150,190,220
```
The generic scorer sums matched component values → `est_value_min/avg/max`, then
`deal_score` vs. effective price. A pack may instead supply a pricing *rubric* (a
prompt) when a table doesn't fit — same output fields.

## Runtime modes (the key tradeoff the skill decides per domain)

- **Pure-data** (regex + tables): offline, free, fast. Run on the full census.
- **LLM-backed** (prompt + judgment): handles messy/ambiguous listings; costs per
  call. Run only on the **candidate funnel** (after price/age/radius filtering),
  never the full census.
- Default = **hybrid**: regex/table fast-path, LLM fallback only when deterministic
  extraction is low-confidence. The pack declares which fields need the LLM.

## The contract (what stays stable so the CLI never changes per domain)

A pack, given a catalog, MUST yield, per listing: `attributes{}` (matching the
declared schema), `est_value_min/avg/max`, `deal_score`, and may add `flags{}`.
The CLI's generic `value`/scorer reads only those. Add a domain → add a pack;
**zero CLI code changes.** Same seam as the marketplace adapters.

## The scam-flag / verify-tier constraint (HARD)

Per memory `feedback_deal-mining-scam-flag-is-verify-not-verdict`: a
too-good-to-be-true `deal_score` (e.g. a $900 RTX 4090 system) is a **VERIFY-HARD,
high-reward signal — never an auto-"scam" drop.** Underpriced outliers from
desperate/clueless sellers are the entire point. Every pack's scorer must:
- quantify the deal **as if real** (value range + score + flip/keep upside),
- surface it in a "high-reward, high-verify" tier with an in-person verification
  checklist, tempered by **seller tenure** (`seller_id` is captured for this),
- never silently exclude or hard-label "scam."

## The generator skill

`generate-deals-pack <domain>` (skill in `skills/` or team-lib):
1. **Sample** — take a scraped catalog for the domain (the funnel of real listings).
2. **Research** — identify the value drivers + source current comps (web), the same
   calibration the original gaming-PC PoC did by hand. Record provenance + date.
3. **Draft** — emit `pack.toml` schema, `extract.toml` regex + guardrails, `value.csv`.
4. **Validate & converge** — run the pack over the sample, check extraction recall
   and value sanity against known comps; iterate until it hits a quality bar
   (same convergence-loop pattern as `new-game` / `create-etsy-toolkit`).
5. **Recalibrate** — re-runnable; refreshes `value.csv` + bumps `calibrated_on`
   when a pack goes past `perishable_after`.

## Build scope (later — stages 5/7)
Generic `deals value --pack <domain>` engine (extractor + scorer reading the
contract) + the gaming-pc pack as the first generated output + the generator skill.
Not in the diff iteration.

## Open decisions
- value.csv table vs. rubric-prompt as the default valuation form (likely both,
  pack declares which).
- Confidence threshold for regex→LLM fallback.
- Pack sharing: user-local only vs. a shared `packs/` in the repo.
- Effective-cost normalization (tower-only + monitor add-on) — generic or per-pack?
