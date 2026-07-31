---
name: brand-site-components
description: "Stage 1 of build-brand-site. Adopt the Untitled UI component set and brand-tune it via tokens (not edits), verifying every variant and state by WCAG math. Mostly ADOPT-then-verify, not build-from-scratch — the token bridge from stage 0 reskins UUI for free. Carries the sharp edges: `untitledui add` overwrites already-customized components and drags transitive bloat, the RSC client-island boundary, functional-border 3:1, and how UUI renders rings as box-shadow layers."
summary: "Component library = adopt UUI + verify contrast per variant/state + brand-tune edge cases. Invoke ext-frontend-design + ext-ui-design-system for aesthetic/system decisions; this adds the UUI-specific layer. Hard rules: add ALL needed components BEFORE customizing any (add overwrites deps — it wiped a custom button once); git status after every add; prune transitive bloat (add input dragged in a 57-file payment-icons tree); math-check tertiary/quaternary text + ALL borders on the warm bg (the eye misses these); a client component's icon-component props force the consuming page to 'use client'."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node, pnpm, python]
tags: [components, untitled-ui, wcag, contrast, accessibility, react-aria, rsc]
---

# Stage 1 — Component Library

Not a from-scratch build. With the stage-0 token bridge, Untitled UI variants already
map to a coherent brand system; this stage is **adopt → verify by math → tune the
edges**.

## Compose first (don't re-derive)
- **Aesthetic / distinctiveness**: `ext-frontend-design` — deliberate type pairing,
  subject-grounded color, restraint in motion; resist generic AI defaults.
- **Design-system structure & tokens**: `ext-ui-design-system`, `ext-theme-factory`.
- **Contrast math**: reuse `build-branded-web-page/scripts/contrast.py`
  (`python3 contrast.py "#fg" "#bg"` for text AA 4.5; `--ui` for 3:1).

## Steps
1. **Add ALL needed components first**, THEN customize: `npx untitledui@latest add
   <comp> -y` copies component + utils fine (its follow-up `npm install` errors are
   harmless — deps pre-installed via pnpm in stage 0).
2. Brand-tune variants via tokens/variant files, not hardcoded colors.
3. Verify EVERY variant + state (default/hover/focus/disabled/invalid) by contrast math.
4. Commit brand-variant additions immediately (so an `add` can't silently revert them).

## The sharp edges (bake in — review caught these)
- **`untitledui add X` OVERWRITES already-customized components X depends on** (adding
  `input` re-copied stock `button.tsx`, wiping a custom `secondary-brand` variant —
  recovered via `git checkout HEAD -- button.tsx`). RULES: (a) add all before customizing;
  (b) `git status` after every add; (c) keep customizations committed.
- **`add` pulls transitive BLOAT** (`add input` dragged in `input-payment` + a 57-file
  `payment-icons/` tree + otp/pin/date/file/number inputs). Prune unused files after
  adding (do it when no reviewer is mid-read).
- **Functional vs decorative borders**: functional UI borders (card/input/button rings)
  must pass 3:1 (WCAG 1.4.11) → warm `neutral-500`+, not the light Brass rule.
- **UUI ring utilities render the border as an INSET box-shadow layer** — when verifying
  via `getComputedStyle`, read the FULL `boxShadow` (the colored ring sits AFTER the
  transparent + skeuomorphic layers); don't truncate.
- **Warm-palette contrast traps the eye misses**: `text-tertiary` at neutral-500 fails AA
  (3.2) → neutral-600 (4.84); light brand borders fail UI 3:1. ALWAYS math-check
  tertiary/quaternary text + every border on the warm bg.
- **`disabled:opacity-50`** reproduces a low-contrast disabled state → tune it.
- **RSC boundary (Next App Router)**: UUI Button is a client component; passing icon
  *component* props (`iconLeading={Icon}`) from a server component throws "Functions
  cannot be passed to Client Components" → the consuming page/section must be
  `"use client"` (or pass elements). Marketing pages mix server shells + client islands.
- **Tailwind v4 scans literal class strings only** — no dynamic `bg-brand-${n}`; enumerate literals.

## Example that maps for free (ONE Mahjong)
UUI Button via token overrides: primary = brand-solid + white (7.1 AAA); secondary =
warm surface + neutral-500 ring (3.48 UI) + muted text; tertiary = neutral-600 (4.84 AA).
Added a **`secondary-brand`** variant = brand outline (ring 6.53 UI + brand-700 text
8.35) — the brand-forward, non-ink-stroke secondary CTA (fixes the classic ink-stroke defect).

## Gate
Every variant + state passes WCAG by math (screenshot to eyeball optional, never the
verification — screenshots render black in WSL; see `brand-site-cohesion-review`). Then →
`brand-site-chrome`.
