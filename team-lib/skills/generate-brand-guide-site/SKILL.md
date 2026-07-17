---
name: generate-brand-guide-site
description: "Render a brand's tokens + guidelines into a polished, self-contained brand-guide.html — visually great documentation generated FROM brand data."
summary: "Step 3 of the brand stack: consumes brand-tokens.json + the narrative sections of brand-guidelines.md and produces a self-contained, brand-expressing HTML brand guide with color, typography, logo, voice, and applied-example sections. LLM-designed, script-verified: a validator rejects any hex or font not present in the tokens file."
version: 1.0.0
template: skill-definition
created: 2026-07-13
last_updated: 2026-07-13
maintainer: pvragon
dependencies: [node]
tags: [branding, brand-guide, html, design-tokens, documentation]
---

# Skill: Generate Brand Guide Site

Turn a brand's machine-readable identity into documentation a human would enjoy reading. This is the presentation layer of the brand stack — it invents nothing:

```
create-brand-guidelines  →  brand-guidelines.md + brand-tokens.json   (data)
compose-branded-template →  resolved doc templates                    (templates)
generate-brand-guide-site → brand-guide.html                          (documentation)  ← this skill
```

Adapted from the `generate-brand-guide` skill by **Zed / North Crow AI** (example at northcrow.ai/brand-guide), shared with permission and credited by request. Its evidence-gathering/interview front half is replaced by our token pipeline; its presentation standards are kept.

## When to Use

- A brand has `brand-tokens.json` and you want shareable, visual brand documentation
- Brand tokens changed and `brand-guide.html` needs regenerating
- Onboarding a designer, contractor, or client to a brand's visual system

## Prerequisites

- `team-lib/context/indexed/companies/{brand}/brand/brand-tokens.json` exists (if not, run `create-brand-guidelines` first — do not hand-build tokens)
- Node.js available

## Core Rules

1. **The tokens file is the only source of color and type values.** Every hex and font-family in the HTML must exist in `brand-tokens.json`. The validator enforces this — a guide that fails validation is not done.
2. **The page must follow the rules it describes.** Design the guide *in* the brand: use `preference.web.*` as the design direction (a `dark-glass` brand gets a dark glassmorphism guide; a `light` brand gets a light editorial one). Never a generic template aesthetic.
3. **Render conditionally, never invent.** Narrative sections (personality, voice, logo usage notes) come from `brand-guidelines.md` verbatim or lightly edited. If a section has no source material, omit it — no fabricated positioning, audience claims, or usage rules.
4. **Self-contained file.** Embed logos as data URIs. The only permitted external requests are Google Fonts (`fonts.googleapis.com` / `fonts.gstatic.com`) for font families that appear in the tokens, with fallbacks so the page degrades gracefully offline.

## Procedure

### Step 1: Load the brand

Read `brand-tokens.json` (all values, coverage stats, computed contrast) and `brand-guidelines.md` (narrative: Brand Personality, color application rules, logo usage notes, voice table, per-content-type notes). Note which tokens carry `$source: derived`/`fallback` — badge these in the guide.

### Step 2: Design and build the page

Follow [references/visual-spec.md](references/visual-spec.md). Section skeleton (omit what has no data):

1. **Cover / overview** — logo, brand name, tagline (if any), version + generation date from `$generated`, coverage stat
2. **Brand personality** — narrative from guidelines + color application rules
3. **Color** — core palette, semantic colors (text/background/border/link/status), heading hierarchy, derivative tints/shades; every swatch shows token path, name, hex, usage, and contrast-safe text
4. **Typography** — real type ramp rendered in the brand fonts with weights, plus font/fallback table
5. **Logo** — variants on their correct light/dark fields, usage notes
6. **Voice & tone** — the four voice attributes; add do/don't examples only if guidelines contain them
7. **Applied examples** — 3–5 patterns picked from `preference.*` enums, filled with real company info from tokens (e.g. document header + signature table style, slide cover, social card, email block). These demonstrate the *preferences*, so a `branded` tableHeaders brand must show branded table headers.
8. **Accessibility** — the computed contrast pairs from tokens with pass/fail levels; state target level
9. **Footer** — provenance: generated from brand-tokens.json (date, coverage %), links to the source files by path

Embed logos: `base64 -w0 <logo.png>` → `data:image/png;base64,...` using the `absolutePath` entries in tokens.

### Step 3: Validate (hard gate)

```bash
node team-lib/skills/generate-brand-guide-site/scripts/validate-brand-guide-html.js \
  --html team-lib/context/indexed/companies/{brand}/brand/brand-guide.html \
  --tokens team-lib/context/indexed/companies/{brand}/brand/brand-tokens.json
```

Checks: no hex/rgb color outside the tokens file, no font-family outside tokens + CSS generics, no external resources beyond Google Fonts (and only for token font families), relative asset paths resolve, basic structure (title, h1, viewport meta). Exit 1 = fix and re-run. Do not hand-wave a failure; if a color is genuinely needed (e.g. a neutral the brand lacks), that's a gap to fix in brand-guidelines.md first, then regenerate tokens.

### Step 4: Visual QA

Render at desktop (~1440px) and phone (~390px) widths — screenshot via Playwright or open in a browser — then work through [references/quality-checklist.md](references/quality-checklist.md). Fix overflow, contrast problems, broken sections, and unreadable print preview.

### Step 5: Hand off honestly

Deliver `brand-guide.html` into `companies/{brand}/brand/`. State which checks ran (validator, widths inspected, checklist items) and any limitations or open gaps — never imply checks that didn't happen. Copy to `my-lib/runtime/deliverables/` only when it's being sent to someone.

### Checkpoint

- [ ] brand-guide.html saved to `companies/{brand}/brand/`
- [ ] Validator passes (0 foreign colors, 0 foreign fonts, assets resolve)
- [ ] Inspected at desktop and mobile widths, no clipping/overflow
- [ ] Applied examples match the brand's preference enums
- [ ] Derived/fallback tokens badged, coverage shown in footer
- [ ] Checks run + limitations reported to the user

## Notes

- **Regeneration is cheap and expected.** When tokens change, re-run this skill; the guide has no hand-maintained state.
- **Provenance badges:** today the parser only marks `$source` on heading colors; as `create-brand-guidelines` v1.3+ provenance labels reach the tokens file, surface them per swatch.
- **This skill does not modify brand data.** Gaps found while building the guide route back to `create-brand-guidelines` (update mode).
