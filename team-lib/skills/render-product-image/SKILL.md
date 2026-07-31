---
name: render-product-image
description: "Produce product images that are both photoreal AND dimensionally correct — by splitting the job: a generative model for the beauty shot, a deterministic vector render for the exact-dimension truth, with pixel-measurement (never eyeballing) as the gate between them."
summary: "Method + reference implementations for generating product/object images. Core rule: generative image models (Gemini 'nano banana' etc.) nail photorealism but CANNOT be driven to exact dimensions/ratios — so use them for the marketing hero and use a deterministic, pixel-controlled render for the dimension-true spec plate. Verify everything by measurement (color ΔE, self-calibrating orthographic geometry), never by visual impression."
version: 1.1.0
template: skill-definition
created: 2026-07-21
last_updated: 2026-07-21
maintainer: your-agent
dependencies: [python, pillow, chromium]
tags: [image-generation, product-render, gemini, nano-banana, self-review, dimensions, measurement]
---

# Skill: Render Product Image

Make an image of a physical product/object that is **both** believable and
**correct**. The trap is treating this as one problem. It is two:

- **Beauty** — does it look like a real photographed object? → a *generative*
  image model excels here.
- **Truth** — are the dimensions, proportions, and part-placement exactly to
  spec? → a generative model FAILS here; a *deterministic* render wins.

Produce both artifacts. Never ship a generative image as if its geometry were
exact.

## When to use

- You need a product mockup / hero shot before real photography exists.
- You need a dimension-accurate visualization or a spec plate for a vendor/RFQ.
- Any "show me what X would look like" with real materials, colors, or sizes.

## Core principle (learned the hard way)

**Generative image models cannot be steered to an exact ratio.** In practice a
target of 0.59 (depth/length) oscillated 0.35 → 0.81 across draws and never
locked, even with the number stated explicitly. And measuring geometry off a
*perspective* generative photo is unreliable (foreshortening + soft shadows).
So:

| Need | Tool | Why |
|------|------|-----|
| Photoreal marketing hero | generative model (Gemini image) | material realism, lighting, believability |
| Exact dimensions / spec plate | deterministic vector render (SVG→Chromium, or PIL) | you control every pixel; ratios exact by construction |

## Procedure

### 1 — Generate the photoreal hero (generative model)

Use the Gemini image API (see **API** below). Grounding is what makes it usable:

- **Exact brand colors** → pass a *solid-swatch reference image* (flat rectangles
  of the exact hexes) and instruct "match these swatch colors." Text hex codes
  alone drift; a swatch pulls it close. (It will still warm/darken under
  "studio light" — a real photo of an exact hex is never pixel-exact; accept a
  small ΔE, verify it, see step 2.)
- **Composition** → pass a prior good image as a second reference for layout.
- **CHANGING GEOMETRY → generate FRESH, do not edit.** Editing a reference
  preserves its geometry, so an edit to "make it thicker" barely moves. To
  change proportions, generate new with the geometry described numerically.
- **Model choice**: `gemini-2.5-flash-image` ("nano banana") is fast and good;
  `gemini-3-pro-image` follows geometry and color instructions noticeably
  better — prefer it when proportions or exact color matter.
- **Describe geometry with ratios + a physical analogy**, not adjectives:
  "thickness = 0.59 × length, nearly as thick as wide, like a chunky bar of
  soap" beats "thick." State part-placement in physical terms ("color only on
  the flat BACK face; all side walls are ivory") — models routinely smear a
  color onto faces you didn't mean.

### 2 — Verify by MEASUREMENT, never by eye (the gate)

You *can* see the image and you *can* be fooled by it — this skill exists partly
because a render that "looked brighter/thicker" measured *worse*. So measure:

- **Color**: sample the region (median of an evenly-lit patch, avoid shadow +
  emblem), compute ΔE (Euclidean RGB distance ok) to the target hex. Report the
  number. Sample boxes must track the actual layout — a box from an old layout
  reads the background.
- **Geometry / the 3D-perception problem**: a human doesn't measure raw pixels,
  they use the object's known shape as a ruler and correct for perspective. Do
  the exact version:
  - **Self-calibrating orthographic view** (robust): ask for one near-orthographic
    elevation (camera perpendicular to a face). That face renders as its true
    rectangle, so its pixel **height÷width = the real ratio directly** — no
    reference object, no perspective math. Measure the bounding box.
  - Reject non-orthographic draws (fill-ratio of tile pixels in bbox < ~0.84 ⇒
    tilted/perspective ⇒ discard) and beware soft shadows inflating the bbox.
  - Single-view metrology (rigorous) is available if you must measure a
    perspective shot: the known face rectangle calibrates the image; the cuboid's
    vanishing points give the depth ratio. Accuracy depends on corner-marking.
- **Discipline**: do NOT report a measured ratio you can't verify, and do NOT
  trust "it looks right." See memory `feedback_no-naive-estimates-without-verification`.

### 3 — Produce the dimension-true artifact (deterministic render)

For exact dimensions, render it yourself so geometry is exact *by construction*:

- SVG → headless Chromium (nice AA, gradients, fonts) or PIL. See
  `scripts/spec_elevation.py` for a parametric side-elevation (length,
  thickness ratio, sub-part ratios, colors, dimension annotations).
- Re-measure the rendered output to confirm — but watch checker bugs (a common
  one: a warm background can pass a naive "bright = object" threshold and
  swallow the bbox; segment by *distance from the sampled background corner*, and
  sanity-check against the values you drew).
- This artifact is the vendor/RFQ/spec truth. Pair it with the hero.

### 4 — Optional: self-evaluation harness

For a *convergeable* attribute (e.g. color), a loop works: generate → measure →
nudge the prompt with the measured-vs-target error → repeat until in tolerance,
surfacing only the winner (`scripts/render_harness.py`). **Do not** expect it to
converge high-variance geometry — that's what step 3 is for. Always `log()` the
per-iteration measurements so a miss is visible, not hidden.

## Gotchas

- Editing preserves geometry; fresh-gen changes it.
- Swatch-grounding gets color close; warm light still shifts it — verify ΔE.
- Perspective + shadows defeat geometry measurement → use an orthographic view.
- Generative models mis-place colors onto wrong faces → state placement physically.
- Your own measurement code is a source of error too (background/foreground
  color collisions) — sanity-check it against ground truth you control.

## Hero-scene guardrails (lifestyle / on-model product shots)

Learned from an adversarial review that HELD 7 ONE Mahjong heroes. A hero is
"beauty," but a *held* hero ships nothing — so bake these into every lifestyle
prompt and self-review each draft against them before handoff:

- **NO third-party brands or copyrighted games ANYWHERE in frame.** Generative
  models love to fill a "game night" table with the games they know — they
  produced a Scrabble board and a Monopoly board unprompted. Explicitly forbid,
  in the prompt: Monopoly, Scrabble, lettered word tiles, playing cards, dice,
  dominoes, any board game / game board, and any real company logo, brand name,
  or product label (beverage, appliance, etc.). Name the ONLY allowed prop
  positively ("the only game shown is genuine mahjong: cream tiles + wooden
  racks"); "if in doubt, keep the table clean."
- **No garbled text on any focal prop.** Models invent gibberish lettering on
  background props (a seltzer can read "SLIM SSLTZER / SLISSTUN"; a second
  tumbler read "ONE MAILJONG / Free the yame"). Prefer PLAIN / UNBRANDED
  background props with no text ("a plain silver can, no logo, no lettering"). If
  a second copy of the product would appear with the mark, either show only ONE
  or require every copy's mark to render cleanly. The product's own slogan must
  render legibly — supply it as a composited design-reference (print file on a
  representative ground) so the model copies the real letters, and re-read the
  draft to confirm spelling.
- **Fixed gallery aspect ratio.** Left unconstrained the model drifts to 5:1
  strips and duplicated-product diptychs. Lock it with
  `generationConfig.imageConfig.aspectRatio` (e.g. `"3:2"` → ~1264×848 landscape;
  values: `1:1 2:3 3:2 3:4 4:3 4:5 5:4 9:16 16:9 21:9`). State "ONE product, ONE
  clean scene, never a duplicated diptych" in the prompt too. **Verify the output
  ratio** — don't assume it honored the field.
- **Audience & tone** (adapt per brand): describe the people concretely (age
  range, "relaxed, warm, genuine, never costume-y") or the model defaults to
  clichés.

Self-review gate for heroes: open every generated PNG and check, per image,
(1) no forbidden prop anywhere, (2) no garbled text on any prop, (3) correct
aspect ratio, (4) the product's own slogan spelled right. A hero that fails any
one is not shippable regardless of how photoreal it looks.

## API (this environment)

- Key: env `GEMINI_AGENTIC_MEDIA_API_KEY` (image-generation quota). A separate
  `GEMINI_FREE_API_KEY` exists for text.
- Endpoint: `POST https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key=...`
  body `{"contents":[{"parts":[{"text":...},{"inline_data":{"mime_type":"image/png","data":<b64>}}]}], "generationConfig":{"responseModalities":["IMAGE"]}}`;
  the response image is base64 in `candidates[0].content.parts[*].inlineData.data`.
- Image models seen live (probe `GET /v1beta/models`): `gemini-2.5-flash-image`
  (nano banana), `gemini-3-pro-image`, `imagen-4.0-*`.
- No AI image model is exposed as a first-class tool in the harness — call the
  API directly (as above). Only Mermaid renders natively, which is not photoreal.

## Reference implementations

- `scripts/gemini_image.py` — generalized generator (prompt + N reference images).
- `scripts/measure_dims.py` — self-calibrating orthographic ratio + color ΔE.
- `scripts/spec_elevation.py` — parametric dimension-true elevation (SVG→Chromium).
- `scripts/render_harness.py` — generate→measure→nudge convergence loop.
- Worked example (mahjong tiles): `projects/one-mahjong/products/mockups/` —
  hero (`tile-set-photoreal-hero-v8.png`), exact spec plate
  (`tile-side-elevation-spec.png`), and the mahjong-specific source scripts.
