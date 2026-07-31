---
name: brand-site-chrome
description: "Stage 2 of build-brand-site. Build the site header and footer — accessible navigation with real routes, a skip-link, current-page state, and a mobile disclosure (via react-aria) — plus a footer that carries the CORRECT canonical domain and any independence/legal disclaimer. Chrome is thin but a11y-critical: it's the one component set present on every page, so a nav defect ships site-wide."
summary: "Header + footer chrome. Invoke ext-frontend-design for the header's distinctive layout; this adds the a11y + canonical-domain specifics. Must-haves: a real skip-to-content link; aria-current on the active route; a keyboard-operable mobile menu (use UUI/react-aria disclosure, don't hand-roll focus trapping); footer canonical URL sourced from brand.config.ts (NOT hardcoded — that's the stale-OG-URL bug's cousin); independence/legal disclaimer if the brand requires one."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node, pnpm]
tags: [header, footer, navigation, accessibility, react-aria, canonical]
---

# Stage 2 — Header / Footer Chrome

Thin stage, high blast radius: chrome is on every page, so any defect is site-wide.

## Compose first (don't re-derive)
- **Header layout / distinctiveness**: `ext-frontend-design` (a nav bar is where generic
  AI aesthetics show first — give it intentional type + spacing).
- **Accessible disclosure primitives**: UUI/`react-aria-components` — don't hand-roll
  focus trapping or menu keyboard handling.

## Steps
1. **Header**: wordmark/logo → canonical `/` route; nav links to REAL routes (from the
   stage-3 sitemap; stub the routes now if needed); one clear primary CTA.
2. **Skip link** first in DOM (`href="#main"`, visible on focus) → the page's `<main id>`.
3. **Current-page state**: `aria-current="page"` on the active link + a visible treatment.
4. **Mobile disclosure**: react-aria disclosure/dialog for the menu — Esc closes, focus
   returns to the trigger, focus stays trapped while open. Verify by keyboard, not eye.
5. **Footer**: canonical domain + secondary nav + independence/legal disclaimer.

## Bake in
- **Canonical URL comes from `brand.config.ts`** (emitted by the stage-0 generator), never
  a hardcoded string — hardcoding it is exactly how the OG/canonical URL goes stale.
- Nav links must be real Next `<Link>` routes (server-navigable), not `<a href="#">`.
- Header/footer are shared chrome → live in `components/marketing/` and take content from a
  `config/nav.ts` data file (copy-as-data; see `brand-site-templates`), not inline JSX.

## Gate
Keyboard-only pass: skip-link works, every nav item reachable + operable, mobile menu
opens/closes/traps focus, active route marked. Canonical domain correct in footer + metadata.
Then → `brand-site-map`.
