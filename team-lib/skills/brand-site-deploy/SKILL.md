---
name: brand-site-deploy
description: "Stage 7 of build-brand-site. Deploy the statically-rendered Next app to Vercel, verify it live by curl (page + routes 200, form endpoint returns its fail-safe 503 or works with the key, OG/canonical correct, no leaked links), and EXTRACT the reusable pieces into the shared kits so the next brand starts from them. Carries the Vercel monorepo gotcha: the build context is web/ only, so brand-tokens.json must be vendored into web/."
summary: "Deploy + verify live + extract. Invoke ext-senior-devops / Vercel best-practices for the deploy specifics; this adds the monorepo + cutover + extract steps. Gotcha: Vercel project root = web/ only → a prebuild that reads repo-root brand/brand-tokens.json fails ENOENT; FIX = vendor brand-tokens.json into web/ (generator prefers web/ copy, falls back to repo-root for local dev, no-ops if neither found). Deploy the app to a SEPARATE project from any existing static site so the live domain is untouched until cutover is approved. curl-verify live. Then extract: component library + token bridge → nextbase-component-kit; sections/shells → nextbase-landing-kit; prove reuse by swapping a second brand's tokens (zero component edits)."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node, pnpm, vercel-cli]
tags: [deploy, vercel, monorepo, verify, extract, nextbase, reuse]
---

# Stage 7 — Deploy + Extract

Ship it, prove it's live, then bank the reusable pieces so brand #2 is cheap.

## Compose first (don't re-derive)
- **Vercel / Next deploy specifics**: `ext-senior-devops` + Vercel React/Next
  best-practices (external). Also `reference_vercel-deploy-workflow` (team memory).

## Vercel monorepo gotcha (the one that bites)
The Vercel project root is **`web/` only** → files OUTSIDE `web/` (the repo-root
`brand/brand-tokens.json`) are NOT in the build context; a `prebuild` that reads them
fails with ENOENT on Vercel. **FIX: vendor `brand-tokens.json` into `web/`** (the app is
the deployable unit, like it vendors Untitled UI). The stage-0 generator already prefers
`web/brand-tokens.json`, falls back to repo-root for local dev, and no-ops (keeps the
committed `brand.css`) if neither is found. **Re-copy `brand/brand-tokens.json` →
`web/brand-tokens.json` whenever the brand changes.**

## Steps
1. **Deploy to a SEPARATE Vercel project** from any existing live site (e.g. `-web` suffix)
   → a preview URL with zero risk to the live domain until cutover is approved.
2. `cd web && vercel deploy --prod --yes --scope <team>`; the domain auto-assigns to the
   latest prod deploy of the project that owns it.
3. **Cutover** (when approved): point the domain at the new project; retire the old
   `site/` after parity. Next handles routing natively (no `cleanUrls` needed).
4. **curl-verify LIVE**: home 200; every key route 200; `_next` assets load; the form
   endpoint returns its fail-safe 503 (or works with the key); OG/canonical point at the
   real domain (not a preview alias); no unwanted links leaked.

## Extract (the payoff — don't skip)
- Component library + token bridge → `Pvragon/nextbase-component-kit`.
- Section library + page shells → `Pvragon/nextbase-landing-kit`.
- **Reusability proof**: swap a second brand's `brand-tokens.json` + fonts, re-run the
  generator, confirm the kit reskins + re-copies with **zero component edits**. Anything
  that needs a component edit = a leaked value; pull it back into a token or content file.

## Gate
Live curl checks all green, OG/canonical correct, form fail-safe verified, extracted kits
build and pass the second-brand swap. Suite complete.
