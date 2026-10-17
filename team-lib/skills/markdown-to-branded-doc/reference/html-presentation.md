---
template: skill-reference
version: 1.0.0
summary: "Manual pathway for branded standalone HTML slide decks: template location, substitution recipe, slide structure rules, component classes, Excalidraw diagram embedding and the required mobile-overflow audit. Split out of markdown-to-branded-doc SKILL.md."
created: 2026-10-06
last_updated: 2026-10-06
maintainer: pvragon
---

## Contents
- Substitution recipe
- Slide structure rules
- Component vocabulary
- Embedding diagrams (Mermaid → Excalidraw)
- Mobile verification (required before publishing)

# HTML Presentation (manual pathway)

The full brand-flexible HTML presentation pipeline is **not yet built** — see backlog `260319-html-presentation-skill.md` for the planned mood-skin + layout-primitives architecture. Until that lands, the working approach is to copy the org-specific hardcoded template, substitute placeholders, and embed the logos as base64 data URIs. The CLI flow (`md-to-branded-doc.js --type html-presentation`) does **not** support this yet.

**Template:** `team-lib/context/indexed/companies/your-brand/brand/assets/templates/html-presentation.html` — standalone file, dark glassmorphism aesthetic, animated wave canvas, keyboard navigation, progress bar. **Mobile-responsive since v2 (2026-07-09):** touch-swipe slide navigation, `dvh`-based card sizing (mobile URL-bar safe), `justify-content: safe center` on slides (overflowing content scrolls from the top instead of clipping — never remove the `safe` keyword), a dedicated phone-portrait regime (≤600px: near-full-viewport card, fluid `clamp()` type, diagram nodes become horizontal icon|title|desc rows, equations wrap as pill rows instead of stacking), and a phone-landscape regime covering every component (incl. `flow-visual` and the inline-styled 3rem slide-top icons via `!important`). Also ships a favicon `<link>` (was missing pre-v2).

**Output location:** `projects/presentations/your-brand/<human-friendly-slug>.html` (no date prefix; published at `prez.example.com/your-org/<slug>`).

**Reference design:** `projects/presentations/your-brand/ai-workspace-intro.html` — the canonical branded HTML presentation; mirror its slide-component patterns, density, and tone.

**Latest worked example:** `projects/presentations/your-brand/portable-agent-package.html` (built 2026-04-29, build script at `my-lib/runtime/.tmp/260429-build-portable-agent-deck.py` — usable as a copy-paste starting point for the substitution flow).

## Substitution recipe

1. Copy the template to the output path
2. Strip the leading `<!-- Branded HTML Presentation Template ... -->` usage-comment block
3. Replace `__TITLE__` (h1 + `<title>` tag — strip HTML for the title tag), `__SUBTITLE__`
4. Replace example slides 2-4 with custom content (the template ships with 4 slides; add more by inserting additional `<div class="slide">` blocks before the navigation comment)
5. Strip the inter-slide `<!-- SLIDE N: ... -->` scaffolding comments after replacement (they're misleading once the example content is gone)
6. Update the static `<div class="slide-counter">1 / 4</div>` to reflect the real slide count (the JS overrides on init, but the static value should still be accurate)
7. Base64-embed `__LOGO_DATA_URI__` and `__FAVICON_DATA_URI__` from `team-lib/context/indexed/companies/your-brand/brand/assets/PV_Logo_onDark.png` and `PV_fav_onDark.png` — **do this AFTER slide insertion** so any new slides referencing `__LOGO_DATA_URI__` (e.g., a closing-slide logo header) also resolve

## Slide structure rules

- **Slide 1 (title)** — `<img class="logo-header">` + `<h1>` with `<span class="accent">` for orange emphasis + `<p class="subtitle">`. No leading icon.
- **Content slides (middle)** — `<h2>` opens the slide (use `<span class="highlight">` for orange emphasis inline). Don't open content slides with a giant decorative icon — that's example-template scaffolding, not the established design language.
- **Closing slide (CTA)** — `<img class="logo-header">` + `<h2>` + body + `<div class="cta-container"><a class="cta-btn">`. The corner logo auto-hides on the first and last slides via the embedded JS.
- **Content density** — keep bullets to 3-5 per slide, ~1 line each. The slide card has firm 4.5rem top/bottom padding (content-safe-zone); overflow scrolls but reads poorly.

## Component vocabulary (use these, not inline styles)

| Component | Class | Use for |
|-----------|-------|---------|
| Bullet list | `ul.bullet-list` | Short bulleted points (orange dot markers) |
| Stat callout | `div.stat-callout` with `span.stat-number` | Big-number callouts (orange) |
| Diagram row | `div.diagram-container` with `div.node.node-{orange,white,teal}` + `i.fa-caret-right.arrow` | 3-node horizontal architecture diagrams (max 3 per row) |
| Memory / feature list | `div.memory-list` with `div.memory-item` (icon + `div.item-text`) | Lists of named pieces with icons (any count) |
| Quote block | `div.quote-block` | Pull-quote with orange left border |
| Equation visual | `div.equation` with `div.equation-part` + `div.equation-op` + `div.equation-result` | Conceptual formulas (A + B + C = D) |
| Grid cards | `div.workspace-grid` with `div.workspace-card.card-{purple,orange,green,blue,teal}` | 2x2 feature/option grids |
| CTA button | `div.cta-container > a.cta-btn` + `p.cta-subtext` | Call-to-action with gradient pill button |
| Flow visual | `div.flow-visual` with `div.flow-row > div.flow-box` + `i.flow-arrow-down` | Vertical step chains |
| Inline orange | `span.highlight` | Orange emphasis in body text (also use this in place of inline-styled `<code>`) |

For 4+ items in a vertical sequence, prefer `memory-list` over multiple `diagram-container` rows — the latter wraps awkwardly without inter-row connectors.

## Embedding diagrams (Mermaid → Excalidraw)

For a real flowchart / architecture diagram (beyond the `diagram-container` /
`flow-visual` primitives), render it with the `excalidraw` CLI and paste the
inline-SVG figure straight into a slide or page. Same engine as the docx/gdoc
diagram embedding, but HTML gets a **transparent, responsive inline SVG** — no
raster, no Drive upload.

```bash
node team-lib/integrations/excalidraw-cli/bin/excalidraw.mjs mermaid diagram.mmd \
  -f html --dark -o out/     # --dark = light strokes for the dark deck
```

- Paste the contents of `out/diagram.html` (a self-contained, transparent,
  centered `<figure>` + inline SVG with fonts embedded) into a `<div class="slide">`.
- It's responsive (fixed width/height stripped, `viewBox` kept) — but STILL run
  the mobile audit below. A very wide diagram is better fixed by a narrower
  **Mermaid** layout (`flowchart TD` instead of `LR`) than by per-deck CSS.
- Light pages/decks: drop `--dark` (the SVG is transparent either way).
- Iterate the diagram LOGIC in Mermaid first — see the [[mermaid-to-excalidraw]] skill.

## Mobile verification (required before publishing)

Every new deck MUST pass `team-lib/skills/mobile-overflow-audit` before pushing:

```bash
node skills/mobile-overflow-audit/scripts/audit.js "file://<abs-path-to-deck>.html" --viewport 844x390   # phone landscape
node skills/mobile-overflow-audit/scripts/audit.js "file://<abs-path-to-deck>.html" --viewport 390x844   # phone portrait
```

Target `worstOverflow` ≤ 5px on both. If a slide still overflows after the template's responsive rules apply, **trim that slide's content** (shorten a paragraph, drop a bullet) rather than adding per-deck CSS — the template rules are the shared fix; content density is the per-deck fix. 568x320 (iPhone SE landscape) is allowed to scroll — `safe center` makes the scroll reach all content.
