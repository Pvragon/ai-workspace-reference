---
name: build-brand-site
description: "Orchestrator for building a multi-page branded marketing SITE (not a single page) on the app-framework path — Next.js (App Router) + Tailwind v4 + Untitled UI + a brand-token→@theme generator, statically rendered, deployed to Vercel. Runs the proven staged methodology (scaffold → components → chrome → sitemap → templates → pages → cohesion → deploy/extract), each stage its own subskill with a hard adversarial-review gate, so any next brand's site is faster and better, not re-derived. Encodes the method proven on the ONE Mahjong onemahjong.org rebuild."
summary: "The parent workflow for a reusable multi-brand site pipeline. New brand = swap brand-tokens.json + fonts; zero component edits. Dispatches to 8 per-stage subskills (brand-site-scaffold/components/chrome/map/templates/pages/cohesion-review/deploy). Each stage builds in isolation → INDEPENDENT adversarial review → gate → assemble. Core invariants: the brand bridge (build-brand-theme.mjs) is the only per-brand surface; verify by MATH not eye (WCAG contrast, scrollWidth vs clientWidth); every user-facing piece passes an independent reviewer prompted to find what's WRONG. Use build-branded-web-page instead for a one-off static HTML page."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node, pnpm, chromium, python]
tags: [web, site, next, tailwind, untitled-ui, brand-tokens, multi-brand, accessibility, wcag, vercel, orchestrator]
---

# Build a Branded Site (app-framework path)

Ship a **multi-page** branded marketing site — component library, chrome, real
routes, templated sections, deployed and verified — that a designer, an a11y
auditor, and a copywriter would each sign off on. Proven on the ONE Mahjong
`onemahjong.org` rebuild. Built so the SECOND brand costs a token swap, not a
re-derivation.

## When to use
- Building a real multi-page branded site on a component framework (marketing site,
  landing suite, product site).
- **Not** for a single static page → use `build-branded-web-page` (simpler, no build step).
- **Not** for a slide deck → use `mobile-overflow-audit`.

## Don't reinvent the wheel — what this suite COMPOSES
Agentic web-building is a crowded, mature space. This suite does **not** re-derive
general web/design craft; it **invokes** the best existing skills for that and adds
only the stack-specific layer (the Untitled-UI token bridge + the hard gotchas + the
gate order). Every subskill names which of these to call:

| For… | Invoke (don't re-derive) |
|---|---|
| Distinctive, non-AI-slop aesthetic direction | `ext-frontend-design` (Anthropic's frontend-design skill) |
| Design-system structure & theming | `ext-ui-design-system`, `ext-theme-factory` |
| Architecture / stack trade-offs | `ext-senior-architect`, `ext-senior-frontend` |
| Interactive / E2E testing | `ext-webapp-testing` |
| Copy de-slop | `ext-humanizer` |
| Security / supply-chain vet | `ext-senior-security`, `scan-for-malware` |
| Brand tokens (the input) | `create-brand-guidelines` (team-lib) |

External best-practice sources this draws from: Anthropic Skills repo
(`github.com/anthropics/skills` — frontend-design, webapp-testing, artifacts-builder),
Vercel React/Next best-practices, WCAG web-accessibility-audit patterns, and the
`awesome-claude-skills` / `awesome-agent-skills` curated lists.

**Our unique, non-duplicated contribution** (the reason this suite exists): the
Untitled-UI + Tailwind-v4 **brand-token→`@theme` generator** (OKLCH gamut-mapped ramp,
guarded primary, surface≠ground) + the stack's sharp edges (`untitledui add`
overwrite/bloat, RSC client-island boundary, Vercel monorepo token-vendoring, WSL2
SwiftShader screenshots) + the fail-safe email form + the adversarial gate order.

> Aesthetic caution surfaced in research: `frontend-design` lists "warm cream bg +
> high-contrast serif + terracotta accent" as a **generic AI default to resist** — which
> a warm brand's tokens can resemble by coincidence. The defense is that the palette is
> **brand-derived** (from `create-brand-guidelines`), not a default reach; still run
> `ext-frontend-design` so the LAYOUT/type/motion stay distinctive, not just the colors.

## The one architectural idea
A single `brand-tokens.json` is the contract; the component kit is an implementation
detail per surface. A generator (`build-brand-theme.mjs`, in `brand-site-scaffold`)
reads the W3C tokens and emits the theme that reskins the entire component set. **The
per-brand surface is that tokens file + the `next/font` imports — nothing else.** Prove
it at the end by swapping a second brand's tokens and confirming zero component edits.

### Two component stacks, one brand (dual-stack)
This suite supports **both Untitled UI** (react-aria; `@theme --color-brand-*`) **and
shadcn/Base UI** (the Nextbase stack; `:root --primary/--background/--ring`). The
generator emits **both theme targets from the same tokens**, so either kit renders the
identical brand. Convention: **shadcn → SaaS app surfaces, Untitled UI → marketing/brand
surfaces**, one kit per page. Full rationale + the Nextbase-repo sync procedure:
**`reference/dual-stack-architecture.md`** (share its "For JP" section with the lead
engineer — the only open decision is how deep Untitled UI reaches).

## The staged pipeline (each stage = a subskill with a hard gate)
Build each stage in isolation → **INDEPENDENT adversarial review** (a separate
reviewer prompted to find what's WRONG) → pass the gate → only then assemble.
Skipping the review or the measurement is how slop and overflow ship.

| # | Subskill | Gate |
|---|---|---|
| 0 | `brand-site-scaffold` | tokens render; brand-600 white-on-solid ≥4.5; surfaces visible |
| 1 | `brand-site-components` | every variant/state passes WCAG by math |
| 2 | `brand-site-chrome` | nav a11y (skip-link, current-page, mobile disclosure); canonical domain |
| 3 | `brand-site-map` | intent per route; sitemap+robots; no dead-end funnels |
| 4 | `brand-site-templates` | sections reusable; copy is DATA not JSX |
| 5 | `brand-site-pages` | scannable (no wall-of-text); funnels wired; fail-safe form |
| 6 | `brand-site-cohesion-review` | whole-site rubric ≥4.0; no overflow at 4 widths; independent review |
| 7 | `brand-site-deploy` | live curl-verified; OG/canonical correct; extract to kits |

## Invariants (hold across every stage)
- **Verify by MATH, never eye.** WCAG contrast (`contrast.py`), overflow
  (`measure_overflow_web.mjs` — scrollWidth vs clientWidth @ 2560/1440/768/375).
- **Screenshots render BLACK in WSL2 headless** (no `/dev/dri`). Fix = SwiftShader
  (`screenshot.mjs` in `brand-site-cohesion-review`), or judge via DOM metrics /
  Pencil canvas. Never assume a screenshot painted.
- **Independent adversarial review** on everything user-facing. Self-approval is not review.
- **Everything reusable is a token or content-data**, never a hardcoded value in a component.
- **Consult `node_modules/next/dist/docs/` before Next-specific code** — recent Next
  diverges from training data (the scaffold drops an `AGENTS.md` saying exactly this).

## Reusability proof (last step, do not skip)
Swap in a second brand's `brand-tokens.json` + fonts, re-run the generator, and
confirm the component library + sections reskin with **zero component edits**. If
anything needs a component edit, that value leaked — pull it back into a token or
content file. This is what makes the pipeline worth more than one site.

## Extract targets
Component library + token bridge → `Pvragon/nextbase-component-kit`; section/page
templates → `Pvragon/nextbase-landing-kit` (see `brand-site-deploy`).

## Related
- `build-branded-web-page` — the single static-HTML-page path (no framework).
- `create-brand-guidelines` — produces the `brand-tokens.json` this consumes.
- `render-product-image`, `mobile-overflow-audit`.
