---
name: brand-site-scaffold
description: "Stage 0 of build-brand-site. Scaffold a lean, statically-rendered Next.js (App Router) + Tailwind v4 + Untitled UI app, vet the supply chain, and stand up THE reusable seam: a brand-token→@theme generator (build-brand-theme.mjs) that reskins the entire Untitled UI component set from one W3C brand-tokens.json. Carries the OKLCH gamut-mapping, guarded-primary, and surface≠page-ground lessons that adversarial review caught on the ONE Mahjong rebuild."
summary: "Scaffold + brand bridge. Ships the generator (vendored): reads brand-tokens.json → emits src/styles/brand.css (@theme: OKLCH brand ramp anchored 600=primary, warm neutral ramp, semantic surface/status/link) + src/brand.config.ts. Key gates the generator enforces: brand-600 white-on-solid ≥4.5 (auto-darkens a light primary), gamut-map by chroma-compression not per-channel clamp, surface (bg-primary)=raised near-white NOT the page ground, functional borders ≥3:1. Wire it into predev/prebuild so brand.css can't drift. New brand = swap tokens.json + next/font imports; nothing else."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node, pnpm]
tags: [scaffold, next, tailwind, untitled-ui, brand-tokens, oklch, theme, supply-chain]
---

# Stage 0 — Scaffold + Brand Bridge

Stand up the app and the ONE per-brand seam. This is the highest-leverage stage:
get the token bridge right and every later stage reskins for free.

## Compose first (don't re-derive)
- **Stack trade-offs** (if not already locked): `ext-senior-architect` / `ext-senior-frontend`.
- **Supply-chain vet** of Untitled UI + its react-aria/tailwind-merge deps:
  `ext-senior-security` + `scan-for-malware` before install (canonical `untitleduico` org).
- **Brand tokens** (the input): produced by `create-brand-guidelines` (team-lib) as a
  W3C `brand-tokens.json`. This stage consumes it; it does not author it.

## Steps
1. Scaffold lean (no Supabase/Stripe/auth for a marketing site):
   `create-next-app --ts --tailwind --app --src-dir --use-pnpm --no-eslint --turbopack`.
   Use the latest **stable** Next (avoid a canary pin unless you need Cache Components).
2. `npx untitledui@latest init --nextjs -y` — it copies theme CSS but **its dep install
   fails on a pnpm project** (shells out to `npm install`). FIX — install with pnpm:
   - runtime: `react-aria-components @untitledui/icons tailwind-merge tailwind-variants motion`
   - dev: `tailwindcss-animate tailwindcss-react-aria-components @tailwindcss/typography`
3. **Drop the generator in** (`scripts/build-brand-theme.mjs`, vendored here). It reads
   `brand-tokens.json` and emits `src/styles/brand.css` + `src/brand.config.ts`.
4. Fonts via `next/font/google` in `layout.tsx` — CSS var names MUST match what the
   generator emits (`--font-<slug>`). This is the one manual per-brand step besides tokens.
5. Import order in `globals.css`: `tailwindcss; theme; typography; brand` (**brand last**
   so its `@theme` wins).
6. **Wire the generator into the build**: `predev`/`prebuild` run
   `node scripts/build-brand-theme.mjs` so the committed `brand.css` can't silently drift.
7. Set root `metadata.metadataBase` = canonical domain from `brand.config.ts` (kills the
   stale-OG-URL bug at the source).
8. Drop a `web/AGENTS.md`: "consult `node_modules/next/dist/docs/` before Next-specific
   code" — recent Next diverges from training data.

## The generator's hard-won rules (adversarial review caught every one)
- **Surface ≠ page ground.** UUI `--color-bg-primary` is the *raised* surface token
  (cards/inputs/menus/secondary-button fills). Setting it to the page color makes every
  surface vanish (1.00 contrast) + dead hovers. Surface = warm `neutral-50`; paint the
  page body from `background.default` separately; hover = `neutral-100`.
- **Ramp anchor: stop 600 = exact brand primary** (UUI paints white on `bg-brand-solid`
  =600). Guard: if white-on-600 < 4.5, darken the anchor until AA and warn.
- **Gamut-map by CHROMA COMPRESSION**, never per-channel clamp — clamp clips saturated
  light tints (R pins 255) and shifts hue muddy. Binary-search max chroma at fixed L,H.
- **Warm neutral ramp hue from a MID-tone token** (Muted), not near-black Ink (atan2
  unstable at low chroma).
- **Functional borders ≥3:1** (WCAG 1.4.11) → warm `neutral-500`+, NOT a light decorative
  Brass Rule (1.67:1, invisible). Keep Brass as `--color-brand-rule` for dividers.
- **Map brand status/link colors** (success→brand tertiary, prose links→brand link) or
  forms/links fall back to off-brand default red/green.
- **Dark mode**: UUI uses a `.dark-mode` class (not `.dark`); leave it dormant unless you
  design + validate a real dark ramp.

## Gate
`node scripts/build-brand-theme.mjs` prints brand-600 + its white-on-solid ratio (must be
≥4.5) and the page ground. `next build` succeeds. A rendered page shows the real page
ground + visible surfaces (not a white void). Then → `brand-site-components`.

## Dual-stack output (shadcn / Base UI target)
The generator is **dual-target**: from the same `brand-tokens.json` it also emits
`src/styles/brand-shadcn.css` — shadcn/Base UI `:root` vars (`--background`/`--foreground`/
`--card`/`--primary`/`--muted`/`--border`/`--input`/`--ring`/`--radius`/`--chart-*`) + a
dark block (unvalidated) + an `@theme inline` mapping. The warm neutral ramp is shared, so
Untitled UI (`brand.css`) and shadcn (`brand-shadcn.css`) render the **identical brand**.
Use `brand.css` for marketing/brand surfaces, `brand-shadcn.css` for Nextbase app surfaces
(one kit per page). It self-checks contrast on the shadcn light pairs (primary/on,
muted-fg/muted, fg/bg) and warns on any AA fail. Distinct `--destructive` red is kept off a
crimson brand primary. Rationale: `../build-brand-site/reference/dual-stack-architecture.md`.

## Ships
- `scripts/build-brand-theme.mjs` — the dual-target generator (zero runtime deps, Ottosson OKLCH).
- `reference/brand-tokens.example.json` — the input schema (ONE Mahjong's, as a worked example).
