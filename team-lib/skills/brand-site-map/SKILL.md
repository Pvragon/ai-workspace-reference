---
name: brand-site-map
description: "Stage 3 of build-brand-site. Define the multi-page route structure with a clear intent per page — including a REAL commerce/shop surface (gated placeholders until payment/fulfillment clears, never a dead-end), traffic-driving SEO pages, and the Next sitemap.ts + robots.ts the base scaffold lacks. This is where a single wall-of-text page becomes an intentful site and where revenue funnels stop dead-ending."
summary: "Sitemap = routes with intent + no dead ends. Invoke ext-content-creator / ext-marketing-strategy-pmm for SEO/traffic intent; this adds the Next specifics + the anti-dead-end rule. Each route has ONE job (convert / inform / rank / capture). Add sitemap.ts + robots.ts (Next doesn't scaffold them). Build a real Shop/catalog surface with a SHOP_LIVE seam: honest 'opening soon' state until H5/H8 (Printify/Etsy) clear, then flip to live links — NEVER link merch to nothing (the #1 funnel defect on the original ONE Mahjong site). Add SEO/landing pages to drive traffic; a shareable research/proof page."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node]
tags: [sitemap, routes, seo, robots, commerce, funnel, information-architecture]
---

# Stage 3 — Site Map

Turn "a page" into "a site." Every route earns its place with one job.

## Compose first (don't re-derive)
- **SEO / traffic intent + information architecture**: `ext-content-creator`,
  `ext-marketing-strategy-pmm` (positioning → which landing pages exist and why).

## Steps
1. **One intent per route** — name each page's single job: convert, inform, rank, or
   capture. If two pages share a job, merge them; if a page has none, cut it.
2. **Real commerce surface, gated not dead**: build the Shop/catalog route now with a
   `SHOP_LIVE` seam — honest "opening soon"/waitlist state while fulfillment is gated
   (H5 Printify / H8 Etsy), flip to live product links when it clears. **Never link merch
   to nothing** — a dead-end funnel is the highest-cost defect (it was the original site's #1).
3. **Traffic-driving pages**: per-topic/variant SEO landing pages; a shareable
   research/proof page; a free-value funnel page (e.g. free cards) that captures intent.
4. **Add `sitemap.ts` + `robots.ts`** — the Next base scaffold ships neither; both are
   required for indexability.
5. Wire the routes into the stage-2 header/footer nav data.

## Bake in
- Gated ≠ absent: a placeholder with a clear "why + when" beats a missing page or a dead link.
- Keep the route list in a `config/nav.ts` data file so chrome + sitemap read one source.
- Static-render everything (marketing) — dynamic only for the form route handler.

## Gate
Every route has a stated single intent; `sitemap.ts` + `robots.ts` present and correct;
no funnel dead-ends (every CTA resolves to a real or honestly-gated destination). Then →
`brand-site-templates`.
