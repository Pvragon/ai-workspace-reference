---
name: build-branded-web-page
description: "Build, polish, and ship a branded static web page (landing/marketing) to a professional bar — with the render+measure-before-ship gate, WCAG contrast verified by math, an accessible fail-safe email-capture form + serverless endpoint, and a humanizer/cut copy pass. Encodes the method proven on the ONE Mahjong onemahjong.org v3 launch so each next site is faster and better, not re-derived."
summary: "A repeatable workflow + reference scripts for shipping a branded static site. Core gates: (1) never deploy unseen — measure document scrollWidth vs clientWidth at 2560/1440/768/375 with headless-Chromium DOM metrics (screenshots render BLACK in WSL/headless, so measure, don't screenshot); (2) verify every hover/focus color by WCAG math, not eye; (3) email capture is FAIL-SAFE (503 when no key — never silently drops) with a non-autofill honeypot + real abuse-control gate before going live; (4) run a humanizer + cut-text pass and an INDEPENDENT copy review before ship. Ships the CDP overflow script (no playwright install needed) + a WCAG contrast util."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node, chromium, python]
tags: [web, landing-page, responsive, accessibility, wcag, overflow, serverless, email-capture, humanizer, deploy, vercel]
---

# Build a Branded Web Page

Ship a branded static site that a designer, an a11y auditor, and a copywriter would all
sign off on — repeatably. Proven on the ONE Mahjong `onemahjong.org` v3 launch.

## When to use
- Building or polishing a branded landing/marketing page (not a slide deck — for
  presentations use `mobile-overflow-audit`).
- Before ANY deploy of a page a human will see — this is the render+measure+review gate.

## The pipeline (each step has a hard gate)

### 1. Build to brand + best practice
Use the brand tokens (colors/type) and best-practice layout: clear hierarchy, generous
whitespace, one primary CTA per view, ~60–75ch line length, accessible tap targets.
**Bake in the responsive safety guards up front** (they prevent the classic overflow bugs):
```css
img { max-width: 100%; height: auto; }
html, body { overflow-x: hidden; overflow-x: clip; } /* hidden=universal, clip wins where supported */
.grid-container > * { min-width: 0; }                /* grid/flex items: default min-width:auto blows out */
/* wide content (tables, code, diagrams) scrolls INSIDE its own box: */
.table-scroll { overflow-x: auto; }
```

### 2. Verify contrast by MATH (never eyeball) — a11y gate
Every text, hover, and focus state must pass WCAG AA (text ≥4.5:1, UI/large ≥3:1).
Don't trust "looks fine" — compute it:
```
python3 scripts/contrast.py "#F5EFE3" "#A62639"        # AA text
python3 scripts/contrast.py "#66549B" "#FBE8DC" --ui   # UI/border
```
Common real bug: a hover state that *drops* contrast (dark text → mid-tone) reads as
"hard to read on hover" even if it technically still passes — fix the affordance. Add
visible `:focus-visible` rings. Keep brand tokens; change only what fails.

### 3. Email capture: FAIL-SAFE form + serverless (build to the provider gate)
People-facing forms must never silently drop an email. Pattern (see
`reference/subscribe.example.js` shape below, proven on ONE Mahjong):
- A serverless endpoint (`/api/subscribe`) that: POST-only; validates the email; has a
  **honeypot with a NON-autofill field name** (never `company`/`name`/`email2` —
  password managers fill those and would drop a real signup — use e.g. `hp_check`);
  **returns 503 `not_configured` when the API key env var is absent** (honest, never
  fake-accepts); an `AbortController` timeout on the provider call; and **leaks no key
  or provider error to the client**.
- The form: real `fetch` submit, hidden honeypot, an `aria-live="polite"` status region
  (`tabindex="-1"`, `.focus()` it on success), states for sending/ok/invalid/503/network,
  double-submit lock, `.btn:disabled` visual state.
- **Abuse control is a MUST before the keyed endpoint is public** — the honeypot only
  stops naive bots; add a Cloudflare Turnstile/hCaptcha challenge or a per-IP rate limit
  (Vercel KV/Upstash), or it can be looped as an email-flood relay. This gates
  form-ACTIVATION, not the deploy (the form stays 503/dormant until the key is set).

### 4. Humanizer + cut the copy — brand-true gate
Run the humanizer pass (leverage `ext-humanizer`): strip AI tells (em-dash overuse,
rule-of-three triads, "not just X but Y", inflated transitions, title-case headings,
puffery/unhedged superlatives). Cut hard — fewer words, scannable. **Preserve the
brand's rulings** (whatever they are — e.g. don't assign the reader specifics, don't
state a competitor's price, keep legal disclaimers). Good copy needs tightening, not a
rewrite — don't flatten the voice.

### 5. INDEPENDENT adversarial review — the anti-slop gate
Spawn a separate reviewer (prompted to find what's WRONG) on anything user-facing: the
form (security + UX + a11y), the copy (AI tells + ruling violations + facts), the page.
Majority-refute or fix. Self-approval is not review. (On the ONE Mahjong launch this
caught a §-ruling copy violation and a security flaw pre-ship on consecutive passes.)

### 6. Render + MEASURE + inspect — never deploy unseen
Screenshots render BLACK in WSL/headless, so measure DOM metrics. Serve locally
(`python3 -m http.server`; `file://` is blocked) and run:
```
node scripts/measure_overflow_web.mjs http://localhost:8000/index.html
# scrollWidth vs clientWidth at 2560/1440/768/375; exit 1 if any width overflows.
# Uses raw CDP via Node's built-in WebSocket — NO playwright install needed; finds a
# Chromium in ~/.cache/ms-playwright or set CHROME=. Wide-but-contained content (a table
# inside overflow-x:auto) shows a rightOverflower but page scrollWidth stays == clientWidth.
```
Only deploy when overflow is FALSE at every width. (Hard lesson: a ~2700px overflow once
shipped unseen.)

### 7. Deploy + verify live
Deploy (e.g. Vercel `vercel deploy --prod --scope <team>` from a staged dir; keep
`cleanUrls:true` if links are extensionless; stage the `api/` dir so functions ship).
Then curl-verify live: page 200, key routes 200, the form endpoint returns its fail-safe
503 (or works with the key), and no unwanted links leaked.

## What this skill captures (so it repeats)
- `scripts/measure_overflow_web.mjs` — the no-install CDP overflow measurement.
- `scripts/contrast.py` — WCAG contrast by math.
- The fail-safe form + serverless + honeypot + abuse-control pattern (step 3).
- The order of gates: guards → contrast → fail-safe form → humanize → **independent
  review** → measure → deploy+verify. Skipping the review or the measurement is how slop
  and overflow ship.

## Related
- `mobile-overflow-audit` — the presentation/slide-deck analog (vertical overflow).
- `render-product-image`, `create-brand-guidelines`, `compose-branded-template`.
