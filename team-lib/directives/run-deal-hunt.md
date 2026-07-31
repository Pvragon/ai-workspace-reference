---
template: directive
version: 1.0.0
summary: "SOP for a one-command marketplace deal hunt — 'find me the best <thing> under $X'. Drives the deals CLI scrape→value→rank end-to-end and produces a ranked deal report with an in-person verify protocol for too-good outliers."
created: 2026-06-25
last_updated: 2026-06-25
maintainer: pvragon
status: active
---

# Directive: Run a Deal Hunt

**Goal:** Turn a plain request — *"find me the best `<thing>` under `$X` near me"* —
into a ranked, decision-ready **deal report**: the few listings actually worth
acting on, why, and (for suspiciously-good ones) exactly how to verify in person.
This is the capstone that makes the `deals` CLI usable in one move.

**When to use:** any "find / hunt / what's the best deal on `<thing>`" request for a
local secondhand marketplace (OfferUp today). For *building* the valuation pack a
domain needs, use `generate-deals-pack` first; for *watching* a query over time,
use `deals watch`. This directive is the one-shot hunt.

## Inputs
- **thing** — what to buy (e.g. "gaming PC", "RTX 4070 rig", "mountain bike").
- **budget** — price ceiling `$X` (the funnel cap).
- **domain pack** — the `deals` pack that values this domain (e.g. `gaming-pc`).
  If none exists, the hunt still runs but ranks by price/proximity only (say so).
- **location / radius** — from `deals` config unless overridden.

## Procedure (Layer 2 drives Layer 3 — the CLI)
Follow the skill `run-deal-hunt` for exact commands and the report template. In brief:
1. **Resolve** the thing → search queries + the domain pack + budget cap.
2. **Scrape ONCE** (cached, polite) into a sample catalog. One sequential scrape;
   then iterate **offline** against the cache — never re-scrape to tweak ranking.
3. **Value** the sample with `deals value --pack <domain>` (gate → extract → value
   → score → `verify_tier`).
4. **Rank** in-domain listings by `deal_score` (best value first), then proximity;
   keep out-of-domain and "gone" items flagged in an appendix — never silently drop.
5. **Write the report** (a deliverable file, not a chat dump) — headline pick(s),
   the ranked shortlist, and the in-person verify protocol for `verify_tier` items.

## Hard rules (non-negotiable)
- **Verify-not-verdict.** A too-good-to-be-true price is a **VERIFY-tier, high-reward
  signal — never an auto-"scam" verdict.** Desperate/clueless sellers posting genuine
  steals are the target. Quantify the deal *as if real* (value range + score + flip/
  keep upside), then give the in-person verify protocol, tempered by seller signals.
  (memory `feedback_deal-mining-scam-flag-is-verify-not-verdict`.)
- **Gone ≠ sold.** A listing that left the feed may be sold, delisted, or out of
  window. Flag it; never claim "sold" unless state says so (see `deals watch`).
- **Rate-limit-safe.** One polite scrape, then offline. Never fan out parallel
  scrapers (that caused the original block).
- **Read-only.** The hunt surfaces deals for a human to act on. It NEVER contacts
  sellers, makes offers, or places deposits.

## Outputs
A ranked deal report at `my-lib/runtime/deliverables/YYMMDD-<thing>-deal-hunt.md`,
plus the valued catalog CSV (intermediate, in `runtime/.tmp/`). A one-paragraph
chat summary points to the report; structured content lives in the file.

## Definition of Done
- The report exists and names a **headline pick** (or an honest "nothing clears the
  bar" if so), with value range, score, distance, and the reason it's the pick.
- Every `verify_tier` / underpriced-outlier item carries the **in-person verify
  protocol** and is quantified as-if-real — none labeled "scam".
- Out-of-domain and gone items are flagged in an appendix, not dropped.
- A methodology note records the pack, its calibration date, and the sample size.
