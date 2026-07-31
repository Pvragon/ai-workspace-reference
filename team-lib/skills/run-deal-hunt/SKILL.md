---
template: skill-definition
version: 1.0.0
summary: "One-command marketplace deal hunt — 'find me the best <thing> under $X'. Drives the deals CLI scrape→value→rank end-to-end and writes a ranked deal report with an in-person verify protocol for too-good outliers. Read-only; scrape-once-cache-iterate-offline."
created: 2026-06-25
last_updated: 2026-06-25
maintainer: pvragon
---

# Skill: Run a Deal Hunt

## When to Use

A user asks for *"the best `<thing>` under `$X`"* on a local marketplace (OfferUp
today). This skill is the orchestration glue: it drives the `deals` CLI
(scrape → value → rank) and turns the result into a **decision-ready report** — the
few listings worth acting on, why, and how to verify the suspicious-good ones in
person. It executes the directive `directives/run-deal-hunt.md`.

Prereqs: `deals` CLI installed + `deals init` run. A domain **pack** for the thing
(e.g. `gaming-pc`); if none exists, build it first with `generate-deals-pack`, or
run the hunt price-only and say valuation was skipped.

## Hard guardrails (read first)
1. **Verify-not-verdict (HARD).** Too-good-to-be-true = a **VERIFY-tier, high-reward
   signal — never an auto-"scam" drop** (memory
   `feedback_deal-mining-scam-flag-is-verify-not-verdict`). Value the outlier *as if
   real*, then attach the verify protocol. Underpriced steals from desperate/clueless
   sellers ARE the target.
2. **Scrape ONCE, iterate OFFLINE.** Detail fetch is the rate-limited step. One
   polite scrape into the cache; do all ranking/valuation against the cached CSV.
   Re-running `deals value` is free.
3. **Never parallel-scrape.** One sequential scrape (default 3 rps / concurrency 3).
4. **Gone ≠ sold; flag, never drop.** Out-of-domain and departed listings go to an
   appendix, never silently removed.
5. **Read-only.** Surface deals for the human. NEVER message sellers, make offers,
   or place deposits.

## Procedure

### 1. Resolve the request
From the user's ask, fix:
- **queries** — the search term(s) that surface the thing (the primary first).
- **budget** `$X` — the funnel cap (`--max-price`).
- **pack** — the domain pack slug (e.g. `gaming-pc`). Confirm it exists:
  `deals value --pack <domain> --help` won't list packs, so check
  `~/.config/deals/packs/<domain>/` or the repo `packs/`. No pack → price-only hunt.
- **location/radius** — config default unless the user gave one (`--location`,
  `--radius`).

### 2. Scrape ONE cached sample (the only live step)
```bash
deals scrape -q "<query>" [-q "<alt query>"] --max-price <X> --enrich \
  --max-pages 4 --out runtime/.tmp/YYMMDD-<thing>-hunt.csv
```
- `--enrich` so the valuer has descriptions; `--max-pages` modest (≈4).
- This is the **only** network step. If it prints a throttle warning, wait and
  re-run — it resumes from cache. Everything below is offline/free.

### 3. Value the sample
```bash
deals value --pack <domain> \
  --in runtime/.tmp/YYMMDD-<thing>-hunt.csv \
  --out runtime/.tmp/YYMMDD-<thing>-valued.csv
```
This populates per listing: `attributes`, `est_value_min/avg/max`, `deal_score`
((value−price)/value; **>0 = below estimated value**), and `flags`
(`verify_tier` when score ≥ the pack threshold; `out_of_domain`; plus guardrail
flags `dealer` / `firm` / `broken`). Out-of-domain rows are flagged, not dropped.

### 4. Rank
Read the valued CSV (offline). Among **in-domain** rows (no `out_of_domain` flag):
- **Primary sort:** `deal_score` descending (best value first).
- **Tie-break:** nearer (`distance_mi`) and fresher (`posted_at`) first.
- **Surface, don't suppress, flags.** `verify_tier` = headline-worthy *with* the
  verify protocol. `firm` = less negotiating room. `broken` / `dealer` = context,
  not disqualifiers. A `price_dropped` listing is a motivated seller — note it.
- Keep a separate list of `out_of_domain` and any departed/`gone` items for the
  appendix.

### 5. Write the report (a deliverable, not chat)
Write `my-lib/runtime/deliverables/YYMMDD-<thing>-deal-hunt.md` using the template
below. Then give the user a one-paragraph chat summary that points to the file.

```markdown
# Deal Hunt — <thing> under $<X> near <location>
_<date> · pack `<domain>` (calibrated <cal-date>) · <N> listings sampled_

## Headline pick
**<title> — $<price>** (est. value $<min>–$<max>, score <+score>) · <distance>mi · <url>
- Why: <below-value math, condition, drop history, proximity>
- Flip/keep upside: <resale comp vs. asking → $ upside, or "solid daily driver at this price">
- Flags: <verify_tier / firm / dealer / price_dropped, each in plain words>

## Shortlist (ranked)
| # | $ | est. value | score | mi | flags | title / url |
|---|---|-----------|-------|----|-------|-------------|
| 1 | … | … | … | … | … | … |
(top ~8 in-domain by score)

## ⚠️ Verify-tier deals (too-good = verify HARD, not "scam")
For each `verify_tier` / far-below-value item — quantified **as if real**, then how to verify:
**<title> — $<price>** (est $<min>–$<max>, score <+score>) · <url>
- As-if-real upside: <$ below value / flip margin>.
- Seller signal: seller_id `<id>`<, "dealer-flagged" / "posts many similar" if so>.
  Account age/ratings aren't in the data — **check them on the listing page** before going.
- In-person verify protocol:
  1. **Cash only.** No deposits, no holds, no wires/Zelle/CashApp before pickup, no shipping.
  2. **Public safe-exchange** — a police-station exchange zone or busy public spot, daytime.
  3. **Inspect live before paying:** power it on; for a PC run **GPU-Z** + **Task Manager
     / Device Manager** to confirm the GPU, CPU, and RAM match the listing; watch for
     artifacts and check temps under load; confirm it posts to desktop and ports work.
  4. **Walk if pressured** — urgency, "ship it", off-platform payment, or specs that
     don't match are the real red flags (not the low price itself).

## Appendix
- **Out-of-domain (excluded from ranking):** <count> — <one-line why>.
- **Departed / gone since sample:** <if known> — "gone ≠ sold".
- **Methodology:** queries, budget cap, pack + calibration date, sample size,
  ranking rule. Note that value tables are perishable.
```

### 6. Converge + summarize
If the headline pick is weak (everything scores negative, i.e. priced above
estimated value), say so honestly — "nothing clears the bar under $X; the closest
is …" — rather than overselling. Don't re-scrape to force a better result; widen
the budget or radius *with the user's say-so* and re-value the same cache if it
covers the wider band, else one fresh polite scrape.

## Output
A ranked deal report in `runtime/deliverables/` + the valued CSV intermediate in
`runtime/.tmp/`. Chat gets a one-paragraph summary and the report path — never the
full dump.

## Notes / known limits
- **Seller tenure:** the catalog carries `seller_id` but not account age/ratings —
  surface the id and the `dealer` flag; the human confirms tenure on-platform.
- **Pack values are illustrative until calibrated** — recalibrate with
  `generate-deals-pack` for trustworthy `est_value_*`. Always print the pack's
  `calibrated_on` date in the report so the reader can weight the estimates.
- Pairs with `deals watch` (set up a watch on the winning query to catch the next
  drop) and `generate-deals-pack` (build/recalibrate the valuation pack).
