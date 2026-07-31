---
name: brand-site-pages
description: "Stage 5 of build-brand-site. Compose each real page from the stage-4 sections, turn any wall-of-text into scannable structured layouts, wire the conversion funnels, and drop in the FAIL-SAFE email-capture form (Next route handler) with proper a11y error association. Where the abstract site becomes the actual ONE Mahjong (or next brand) pages."
summary: "Compose pages + de-slop copy + wire funnels + fail-safe form. Invoke ext-humanizer + ext-content-creator for the copy pass (strip AI tells, cut hard, preserve brand rulings). Reuse the fail-safe form contract from build-branded-web-page: 503-when-no-key (never fake-accept), non-autofill honeypot, timeout, no key/provider leak — ported to a Next route handler (export async function POST). a11y: route field errors through UUI Input's hint+isInvalid so react-aria wires aria-describedby (don't hand-roll a detached error <p>); clear stale invalid on valid input. Map error text to a darker red (default vivid red-600 fails AA on a warm bg)."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node, python]
tags: [pages, copy, humanizer, email-capture, forms, accessibility, funnel]
---

# Stage 5 — Individual Pages

Compose the real pages; make them scannable; wire the money paths; ship the form safely.

## Compose first (don't re-derive)
- **Copy de-slop**: `ext-humanizer` — strip em-dash overuse, rule-of-three triads,
  "not just X but Y", inflated transitions, title-case headings, puffery. Cut hard.
  **Preserve the brand's rulings** (legal disclaimers, don't-assign-the-reader-specifics,
  don't-state-a-competitor's-price). Tighten, don't flatten the voice.
- **Content strategy / SEO copy**: `ext-content-creator`.
- **The fail-safe form pattern + scripts**: `build-branded-web-page` (step 3 + `contrast.py`).

## Steps
1. Compose each route from stage-4 sections + its content-data file.
2. **Wall-of-text → scannable**: headings, eyebrows, short blocks, one idea per section,
   pull the dense research/manifesto prose into structured layouts.
3. **Wire the funnels**: free-value capture, shop links (respecting the `SHOP_LIVE` seam),
   one clear primary CTA per page.
4. **Fail-safe email form** as a Next route handler:
   - `export async function POST(request: Request): Promise<Response>`; `runtime="nodejs"`.
   - POST-only; validate email; **non-autofill honeypot** (`hp_check`, off-screen +
     aria-hidden + tabindex -1 — never `company`/`name`/`email2`, password managers fill those).
   - **503 `not_configured` when the key env var is absent** (honest, never fake-accepts).
   - AbortController timeout on the provider call; **leak no key or provider error**.
   - Cap the request body (reject `content-length` over a few KB before parsing).
5. **Abuse control is a real launch gate** (not closable in code alone): honeypot is
   defeated by omitting the field → add Turnstile/hCaptcha or per-IP rate-limit (KV) before
   the keyed endpoint goes public. The form stays 503-dormant until then (not yet exploitable).

## a11y / contrast (bake in)
- **Associate field errors** via UUI Input's `hint` + `isInvalid` (HintText uses
  `slot="errorMessage"` → react-aria wires `aria-describedby` automatically). Don't
  hand-roll a detached error `<p>`.
- **Clear stale `invalid`** in onChange the moment the value passes (else aria-invalid lies).
- **Error text**: map `--color-text-error-primary`→`red-700` (default vivid red-600 =
  4.23:1 fails AA on a warm surface). Dormant/info (the 503 "cards are free" note) is
  benign → style neutral, reserve red for real errors.
- **Verify lab() colors** (Tailwind v4 emits `color: lab(...)`): `Y=((L*+16)/116)^3`,
  contrast from that when canvas readback is blocked.

## Gate
Pages are scannable (no wall-of-text), every funnel resolves, copy passes an INDEPENDENT
copy review (AI tells + ruling violations + facts), the form is fail-safe + a11y-correct.
Then → `brand-site-cohesion-review`.
