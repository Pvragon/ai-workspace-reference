---
template: skill-definition
version: 1.0.1
summary: "Generate (or recalibrate) a consumer-deals domain pack — attribute extraction + value tables + scoring — for any new product domain. Scrape-once-cache-iterate-offline so it never hits rate limits."
created: 2026-06-24
last_updated: 2026-08-01
maintainer: pvragon
---

# Skill: Generate a consumer-deals Domain Pack

## When to Use

Use this when you want the `deals` CLI to **value and rank** listings in a new
domain (gaming PCs, mountain bikes, DSLR lenses, power tools, sneakers…). The CLI's
scrape layer is domain-blind; a **pack** teaches it what to extract and how to value
it. This skill produces (or recalibrates) that pack.

Prereqs: `deals` CLI installed and `deals init` run (see
`team-lib/integrations/consumer-deals/`). Read `PACK_SPEC.md` there for the contract.

## Hard guardrails (read first)

1. **Scrape ONCE, then iterate OFFLINE.** Detail fetching is the rate-limited step.
   Do a single funnel scrape into the cached catalog, then do *all* extraction /
   valuation / tuning against that cached sample — zero further API calls. The CLI
   caches details (`<config>/cache/`); re-running `deals value` is free.
2. **Never fan out parallel live scrapers.** One sequential, polite scrape (default
   3 rps / concurrency 3). Parallel scrapers are what caused the original block.
3. **Verify-not-verdict (HARD).** A too-good-to-be-true `deal_score` is a
   **VERIFY-tier, high-reward signal — never an auto-"scam" drop**
   (memory `feedback_deal-mining-scam-flag-is-verify-not-verdict`). The pack flags
   `verify_tier`; it never excludes. Value underpriced outliers *as if real* + a
   verification checklist, tempered by seller tenure (`seller_id`).
4. **Value data is perishable.** Stamp `calibrated_on`; set `perishable_after`.
   Recalibration = re-run this skill, refresh `value.csv`, bump the date.

## Procedure

### 1. Define the domain
Pick a `domain` slug (e.g. `mountain-bike`), the **search queries** that surface it,
a sensible **price ceiling** (funnel cap), and the **value-driving attributes**
(what makes one worth more — for bikes: frame material, drivetrain tier, wheel size,
brand). Write these down; they become the schema.

### 2. Scrape ONE cached sample (single live step)
```bash
deals scrape -q "<query1>" -q "<query2>" --max-price <cap> --enrich \
  --max-pages 4 --out <domain>-sample.csv
```
- `--enrich` for descriptions (extraction needs them), `--max-pages` modest.
- This is the **only** time you touch the network. The details are now cached;
  everything below re-reads the CSV / cache for free. If it prints a throttle
  warning, wait and re-run — it resumes from cache.

### 3. Research value drivers (web — not rate-limited)
For the value-driving attributes, gather **current used-market comps** (sold
listings, marketplace ranges, reference sites). Capture min/avg/max per
component/feature **and the sources + date**. This is the calibration that makes
estimates real.

### 4. Draft the pack files
Create `~/.config/deals/packs/<domain>/` (user) or the repo `packs/<domain>/`:

- **`pack.toml`**
  - `[meta]` — domain, version, `calibrated_on` (today), `perishable_after`, `value_sources`.
  - `[domain]` — `include` (must look like the thing) + `exclude` (hard non-domain
    items). **Gate on the TITLE only.** Do NOT put component nouns in `exclude`
    (a real item lists its specs in the title). Coarse is fine — step 6's LLM pass
    refines edges.
  - `[extract]` — `text_sources`, `prefer_source = "title"`, `skip_phrases`
    (aspirational/compat phrasing: "upgrade to", "compatible with", …).
  - `[extract.regex]` — one pattern per value-driving attribute.
  - `[scoring]` — `verify_tier_threshold` (e.g. 0.55).
  - `[attributes]` — declared schema (`drives_value`).
- **`value.csv`** — `feature,key,min,avg,max` rows (+ a `base,base,…` baseline for
  the rest of the item), from step 3's comps.

Model it on the shipped `packs/gaming-pc/` pack.

### 5. (If needed) LLM-assist extraction the regex misses
Regex handles clean titles; messy listings need judgment. Where regex recall is low,
**read the cached sample yourself** and either tighten the regex or write the parsed
attributes back into the catalog's `attributes` column. The CLI engine stays
deterministic; you supply the judgment offline. No API calls.

### 6. Validate OFFLINE against the cached sample, and converge
```bash
deals value --pack <domain> --in <domain>-sample.csv --out <domain>-valued.csv
```
Check three things and iterate **on the same cached sample** until each passes:
- **Extraction recall** — are the value-driving attributes parsed on most genuine
  items? (Fix regex / skip_phrases.)
- **Gate precision** — are non-domain items (`out_of_domain`) excluded, and genuine
  items kept? (Fix `include`/`exclude` — title-only.)
- **Value sanity** — do `est_value_avg` land near your step-3 comps? Are the top
  `deal_score` / `verify_tier` items plausible real deals, not artifacts? (Fix
  `value.csv`.)
Each `deals value` run is free (cache) — loop freely. Stop when all three hold on
the sample.

### 7. Stamp + record
Confirm `calibrated_on` = today, `value_sources` lists real provenance. Note the
sample size and the residual gaps (attributes the regex can't get, value keys still
missing) so the next recalibration knows where to look.

## Output
A `packs/<domain>/` pack (`pack.toml` + `value.csv`) that `deals value --pack
<domain>` consumes, plus a one-paragraph report: what it extracts, how it's
calibrated (sources + date), the validation numbers on the sample, and known gaps.

## Recalibration
Re-run steps 2–7 when a pack is past `perishable_after`, reusing the cache where
fresh. Refresh `value.csv`, bump `calibrated_on` + pack `version`.
