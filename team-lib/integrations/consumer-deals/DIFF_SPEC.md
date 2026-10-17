---
template: cli-design-spec
version: 0.2.0
summary: Design spec for `deals diff` + `deals watch` — rerun a scrape and compute the delta (new / gone / sold / unlisted / price-changed) against a prior catalog, then alert. The detection primitive underneath automated deal-watching.
created: 2026-06-22
last_updated: 2026-06-25
maintainer: your-agent / the-operator
status: BUILT (v0.5.0) — `diff` + `watch` (incremental/full) + sold-state shipped
---

# `deals diff` + the path to deal-watching — Design Spec

## Purpose

Rerun an existing search and answer "**what changed?**" — which listings are new,
which are gone, which moved in price — by comparing two catalogs. This is the
domain-agnostic detection primitive that automated **deal-watching** is built on:
scan on an interval, detect a new/dropping listing that matches criteria, alert
the human to jump on it fast.

It delivers value with **zero valuation work** (pure delta on the catalog), and it
surfaces a signal the single-scrape path can't: **price changes between runs** —
even when OfferUp shows no strike-through. A listing that drops three times in two
weeks is the strongest motivated-seller signal we have.

## Diff model

Key every listing by `listing_id`. Compare an **old** catalog to a **new** one:

| Category | Definition | Notes |
|---|---|---|
| `new` | id in new, not in old | the high-value bucket for watching |
| `gone` | id in old, not in new | **gone ≠ sold.** Could be sold, delisted, expired, paused, or fell out of the radius/age window. Label it `gone`, never claim `sold`. |
| `price_drop` | id in both, `new.price < old.price` | `price_delta < 0`; the motivated-seller signal |
| `price_rise` | id in both, `new.price > old.price` | seller testing higher; usually deprioritize |
| `unchanged` | id in both, same price | |

Edge cases: missing price on either side → `unknown` (don't fabricate a delta).
`--fast` catalogs (no distance/age) still diff fine on id + price.

## Command surface (this iteration)

```
deals diff [OLD.csv] [NEW.csv]        # explicit pair
deals diff                            # auto: two most-recent catalogs in catalogs_dir
deals diff --new-only                 # just the new listings (watcher's core view)
deals diff --drops                    # just price drops
deals diff --out delta.csv            # machine-readable delta (change + price_delta columns)
deals diff --min-drop 10              # only price drops >= N% (or $N with --min-drop-amt)
```

- Default report: a compact summary + the `new` and `price_drop` buckets (the
  buckets a hunter acts on), sorted by relevance (largest drop / cheapest first).
- `--out` writes one row per changed listing with two extra columns: `change`
  (new/gone/price_drop/price_rise) and `price_delta`. Gone rows carry the old-side
  record; everything else carries the new-side.
- Exit code: `0` always on a successful diff; a `--exit-on-change` flag (for cron
  use) returns non-zero when there are new/dropped listings, so a scheduler can
  branch on "something happened."

## Persistence — light now, SQLite later

- **Now:** catalogs already land in `catalogs_dir` with timestamped names. `diff`
  with no args picks the two most recent. This needs no new storage.
- **Per-query state (next):** to diff "this query vs its own last run" (not just
  the two most-recent files of any query), tag catalogs by a `(site, query,
  location)` key and resolve the previous catalog for that key. A small
  `state/<key>.json` (last-catalog pointer) or a filename convention.
- **SQLite (Stage 8):** one row per (listing_id, observed_at) → full
  **price-history over time**, incremental scrape, dedup across many runs. This is
  where "dropped 3× in two weeks" becomes a first-class query. The diff command's
  categories are the same; only the backing store changes.

## The watch pathway (what diff is the foundation for)

Polling is the only option (OfferUp has no push/webhook), so the design goal is
**minimize each poll**, not poll harder. Two cadences over the one diff primitive:

1. **New-listing poll (fast / cheap / every few min):** an *incremental
   newest-first sweep* — sort the feed by newest, fetch pages only until hitting an
   already-seen `listing_id`, then stop. Pulls the new head of the feed, not the
   whole census. Detail-fetch + value only the genuinely-new ids. This is what
   makes "jump on it super fast" affordable and polite (low block risk).
2. **Price/gone re-scan (slower / hourly or daily):** re-scan the tracked set so
   price drops and disappearances on *existing* listings are caught (a newest-sort
   poll can't see those).

`deals watch` (future) = the diff primitive + a scheduler (`/loop` or `/schedule`)
+ a notify sink (push notification / ClickUp Pulse) + an optional per-domain
`--value` pass so the alert says *how good* the deal is, not just *that it's new*.

**Hard boundary:** read/analysis only. The watcher **never contacts sellers or
places offers.** "Jump on it" = alert the human instantly with the deal summary +
listing URL; the human acts. The tool surfaces; the person decides.

## Build scope — THIS iteration

`deals diff` (pairwise, auto-pick latest two, `--new-only`/`--drops`/`--out`/
`--min-drop`/`--exit-on-change`) + a `deals/diff.py` module + tests. No new
storage, no scheduler, no alerting — those are the `watch` milestone. The
incremental newest-first sweep is a `scrape` enhancement that lands with `watch`.

## Sold-state — VERIFIED 2026-06-25 (built)

The blanket `gone` bucket now splits, using OfferUp's verified availability fields
(`state` / `isSold` / `isArchived` — NOT `soldAt`, which doesn't exist):

| Category | Definition |
|---|---|
| `sold` | `state` LISTED → SOLD (still resolves). A real sale. |
| `unlisted` | LISTED → UNLISTED (seller pulled it; NOT sold). |
| `gone` | `listing: null` only — genuine deletion. Still "≠ sold". |

`diff_catalogs` splits in-place transitions directly; `reclassify_gone(result,
state_lookup)` re-queries departed ids' current `state` (a cheap gone-ids-only
pass) to split them. Full findings: `runtime/.tmp/260622-deals-cli-probe/
FINDINGS-soldstate.md` + memory `reference_offerup-sold-state-fields`.

## Resolved decisions
- **Newest-first sort:** `{"key":"sort","value":"newest"}` IS honored — but it's
  recency-WEIGHTED, not strict postDate-desc. So `watch` bounds the incremental
  poll to `--pages` (default 2) instead of trusting "stop on first already-seen id".
- **Per-query keying:** `deals/watchstate.py` — a JSON pointer per `(site, query,
  location)` under `<config_dir>/watch/`, holding the last-catalog path.
- **Driver:** `deals watch` does ONE poll; the cadence is external (`/loop` or
  `/schedule` re-invokes; `--exit-on-change` returns 10 for cron branching).
- **Alert sink:** pluggable `deals/notify.py`; `--notify email --email-to ADDR`
  ships via the workspace `gws gmail +send` helper (fails soft; stdout always).
