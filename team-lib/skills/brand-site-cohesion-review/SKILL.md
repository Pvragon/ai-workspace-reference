---
name: brand-site-cohesion-review
description: "Stage 6 of build-brand-site. Review the whole assembled site as ONE artifact against web + brand rubrics: brand-token fidelity, WCAG AA (measured), responsive with zero overflow at 2560/1440/768/375, performance budget, no dead ends — plus an interactive pass and a final INDEPENDENT adversarial review. Ships the WSL2 SwiftShader screenshot tool that actually renders (default headless Chromium paints black here)."
summary: "Whole-site gate. Invoke ext-webapp-testing for the interactive/E2E pass + ext-code-reviewer / ext-senior-qa for the review. Measure, don't eyeball: reuse measure_overflow_web.mjs (scrollWidth vs clientWidth @ 4 widths, no playwright install needed) + contrast.py from build-branded-web-page. Screenshots render BLACK in WSL2 (no /dev/dri) → use the vendored screenshot.mjs (forces SwiftShader software GL) to actually see the build, or judge via DOM metrics / Pencil canvas. Run against the web/brand rubrics (avg ≥4.0) + Lighthouse (≥95 a11y/perf/best-practices/SEO). A separate reviewer prompted to find what's WRONG signs off — self-approval is not review."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node, chromium, python]
tags: [review, cohesion, wcag, responsive, overflow, lighthouse, webapp-testing, wsl, screenshot]
---

# Stage 6 — Assembly + Cohesion Review

Each stage passed in isolation; now judge the COMBINATION. This is the anti-slop gate.

## Compose first (don't re-derive)
- **Interactive / E2E pass**: `ext-webapp-testing` (drive the real routes, forms, nav).
- **Code + quality review**: `ext-code-reviewer`, `ext-senior-qa`.
- **The overflow + contrast scripts**: `build-branded-web-page/scripts/`
  (`measure_overflow_web.mjs`, `contrast.py`).

## Verify by MATH, never eye
- **Responsive**: `node measure_overflow_web.mjs http://localhost:3000/<route>` — checks
  scrollWidth vs clientWidth @ 2560/1440/768/375; exit 1 on overflow. Raw CDP, no
  playwright install. (Wide-but-contained content inside `overflow-x:auto` is fine — page
  scrollWidth stays == clientWidth.) A ~2700px overflow once shipped unseen; don't repeat it.
- **Contrast**: spot-check final rendered colors with `contrast.py` (and the lab() formula
  where getComputedStyle returns lab).
- **Brand fidelity**: computed colors/fonts trace to tokens, not stray hardcodes.

## Screenshots that actually render in WSL2 (root-caused + fixed)
Default headless Chromium paints **black** in WSL2 (no `/dev/dri` GPU nodes). Fix = force
SwiftShader software GL. Use the vendored tool:
```
node scripts/screenshot.mjs http://localhost:3000/ 375,768,1280
```
It finds a Chromium in `~/.cache/ms-playwright` (or `CHROME_PATH`) and renders any route(s)
at the given widths. Use it to EYEBALL the build; still MEASURE for the pass/fail gate.
(For aesthetic judgment you can also render via Pencil canvas.)

## Whole-site rubric
Review as one artifact against `harness/rubrics/web.md` + `brand.md` (avg ≥4.0):
brand-token fidelity · WCAG AA measured · perf budget (<~200KB) · responsive @4 widths ·
correctness · **no dead ends**. Add Lighthouse (target ≥95 a11y/perf/best-practices/SEO).

## Independent adversarial review (the gate)
Spawn a SEPARATE reviewer prompted to find what's WRONG across the whole site (cohesion,
a11y, funnels, copy rulings, security). Majority-refute or fix. In this WSL env, builder/
reviewer subagents misfire ~30-40% (0 tool_uses / garbage) → just relaunch; the successful
passes do excellent work.

## Gate
Rubric avg ≥4.0, zero overflow at all four widths, Lighthouse targets met, interactive pass
green, independent reviewer signs off. Then → `brand-site-deploy`.

## Ships
- `scripts/screenshot.mjs` — SwiftShader render that works in headless WSL2.
