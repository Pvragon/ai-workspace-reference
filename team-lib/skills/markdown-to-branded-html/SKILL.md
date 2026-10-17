---
template: skill-definition
name: markdown-to-branded-html
description: "Render markdown into a self-contained branded HTML document, with styling taken only from the composed template; the build fails on off-token colors, sub-AA contrast or humanizer-gate copy, and mermaid becomes zoomable inline SVG. Use when asked for a branded report, walkthrough, handoff page or explainer in HTML, especially for prez.example.com."
version: 1.1.3
summary: "Render markdown to a self-contained branded HTML document, the default for any branded page read top to bottom: reports, walkthroughs, handoff pages, prez.example.com documents. Styling comes only from the composed template. The build fails on off-token colors, sub-AA contrast, or copy that trips the humanizer gate. Mermaid becomes zoomable inline SVG."
created: 2026-09-03
last_updated: 2026-10-16
maintainer: pvragon
dependencies:
  - skills/compose-branded-template
  - skills/publish-to-prez
listing: name-only
category: documents
---

# Markdown to Branded HTML (document format)

The **default format for a branded HTML document or artifact** — anything that is read
top to bottom rather than presented slide by slide. Sibling of `markdown-to-branded-doc` (docx /
Google Docs / Slides) and of the `html-presentation` deck pathway. Settled with the operator on 2026-09-03
on the Acme Health billing-classification walkthrough (`prez.example.com/northwind/260903-billing-classification-walkthrough`),
which is the reference page.

## When to use

- A branded HTML page that is a **document**: a report, a process walkthrough, a handoff page, an
  explainer, a status page — especially anything headed for `prez.example.com` (see `publish-to-prez`).
- The source is, or can be, **markdown** with optional mermaid diagrams.

**Not for:** slide decks (`markdown-to-branded-doc` → `html-presentation`), marketing / landing pages
(`build-branded-web-page`), or multi-page sites (`build-brand-site`).

## The format (what the template encodes)

`context/indexed/companies/{brand}/brand/templates/html-document.json`, composed by
`compose-branded-template` from `brand-tokens.json`. The renderer reads **only** this file for
colour, type and spacing — never hand-picked tokens (that is the failure the 2026-07-30 memory-deck
rebuild corrected, and it recurred on 2026-09-03 before this skill existed).

| Rule | Value (this workspace) | Why |
|---|---|---|
| Dark only | body on near-black `#080E10`, cards `#112328` | the brand's dark theme; the composed template has no light variant |
| **One tint for every coloured text and numeral** | `color.derivative.primary.tint3` `#86C1D6` | it is the tint of the primary that still reads as the primary on dark. Lighter tints read as white, the mid tint reads as sky blue, the orange reads harsh (chromostereopsis) |
| **Accent (orange) on non-text only** | header / footer rules, kicker dashes, callout side lines, viewer bar edge, link underlines | keeps the orange in the brand without small orange text on dark |
| **3:1 heading rhythm** | H2 66/22, H3 48/16, H4 36/12 px above/below | a heading belongs to what follows it; elements after a heading carry no top margin |
| Headings are plain text | H2 27px/800, H3 21px/750 with a numeral badge for `### 1. …`, H4 13.5px uppercase kicker with an accent dash | bands, boxes and other "departures from raw text" were tried and rejected as not premium |
| Wave background | the template's five-layer canvas at its own alphas, off under `prefers-reduced-motion` | the brand's ambient motion, subtle enough for a long read |
| Brand font embedded | Noto Sans variable woff2 (latin, 300–700) as a data URI | self-contained; no webfont CDN |
| Diagrams | inline SVG (native mermaid renderer, hand-tuned `<br/>` breaks honoured), white canvas, click-to-open viewer with drag pan, wheel / pinch / double-click zoom, Fit / 100%, Esc | diagram palettes are tuned for white; a page-width diagram is unreadable without zoom |
| Gates | every hex / rgb in the output must be a brand token (or the template's near-black); every text pair in `accessibility.contrastGate` must clear its WCAG 2 minimum; the copy must clear the humanizer + self-narration pass | measured, not eyeballed; the build fails otherwise |

## Usage

```bash
python3 skills/markdown-to-branded-html/scripts/md_to_branded_html.py <input.md> <output.html> \
  [--brand your-brand] [--type html-document] \
  [--diagrams-dir DIR] [--captions captions.json] \
  [--eyebrow "Client · Project · Topic"] [--lede "one-paragraph standfirst"] \
  [--meta "Reviewed 2026-08-28|v0.7|Updated 2026-09-03"] [--accent-words 2] \
  [--footer "provenance sentence"] [--share-header] \
  [--no-copy-pass] [--copy-ok] [--copy-model sonnet]
```

- `--diagrams-dir` — where `<!-- diagram: name -->` markers find `name.mmd` (the source of truth for
  hand-tuned diagrams). Fences without a marker or a source file are rendered from the fence body.
- `--captions` — `{"name": ["Title", "subtitle"]}`; a figure directly under an H4 of the same title
  shows only its subtitle.
- `--accent-words N` — the last N words of the title in the heading tint.
- `--share-header` — adds the prez share microheader (`/prez-header.js`); only for prez pages.
- Frontmatter `version` / `last_updated` feed the meta line when `--meta` is not given.
- `--no-copy-pass` / `--copy-ok` / `--copy-model` — the copy gate; see below.

## The copy gate (on by default)

Every build is a copy review before it is a render. The gate runs **before** rendering, so a
failure never leaves an HTML behind.

**What it does.** It pulls out the prose a reader actually reads — the markdown body with
frontmatter, fenced code, diagram fences and raw HTML tags removed (tag *text* kept, table cells
flattened to sentences), plus the `--title`, `--eyebrow`, `--lede`, `--meta` and `--footer`
strings — and sends it to `claude -p` with two references loaded **verbatim**:

| Reference | What it catches |
|---|---|
| `skills/_external/blader-humanizer/SKILL.md` (third-party, never edited, never re-implemented as regexes) | the vocabulary and construction tells: "is a testament to", em-dash overuse, rule of three, negative parallelism, promotional language, -ing analyses, weasel attributions, generic positive conclusions |
| `skills/humanizer-supplement/SKILL.md` | the **stance** tells: copy that talks about the document instead of its subject — explaining its own conventions / structure / navigation, narrating its method or how it was built, flourish where a plain label was the job. The knowing aside moved to the humanizer skill (pattern 2) when it was bumped to v3.0.0. |

The judge returns strict JSON. Findings print as
`COPY <rule> | "<quote>" -> "<rewrite>" (<why>)`, the full report is written to
`<output>.copy-report.json`, and the build **exits non-zero without writing the HTML**. A clean
run prints one line: `copy pass: clean (N sentences checked, sonnet, 12s)`.

**Flags.**

| Flag | Use |
|---|---|
| `--no-copy-pass` | skip entirely — for non-prose artifacts (a generated grid, a data table with no sentences) |
| `--copy-ok` | build anyway, **after a human has read the report**; the report is written with `"acknowledged": true` |
| `--copy-model NAME` | default `sonnet`. The judge is one turn over ~30–60 KB of prompt, ~10–90 s. |

**`claude` missing, erroring, or timing out (240 s) FAILS the build.** A gate that silently
passes measures nothing. Use `--no-copy-pass` deliberately, not as a workaround.

### What it cannot catch

- **A clean report is not proof.** Measured 2026-09-15 on the `prez.example.com/travel` San Diego
  guide: the humanizer was run, the page was declared "clean, zero tells", and the operator then flagged
  **nine** instances by hand — which is the whole reason the stance reference exists. Read the page.
- **Flourish headings** are only caught when the flourish is on the surface. "The coast, to scale"
  reads as a plain label unless the judge can see that the section is a map; it has the copy, not
  the layout.
- **Stance without surface markers.** A sentence that narrates the document but uses no
  give-away construction ("Each cell is an item from the working plan") is caught only because the
  reference spells that sub-case out. A novel shape will get through until the reference grows it.
- **Redundancy and overclaiming** — a column that restates another column, an eyebrow asserting a
  fact not in evidence — are structural, and the gate sees text only.
- **It is one judge, one turn.** Re-running can move the finding set at the margin. Treat an empty
  result as "nothing obvious", never as a sign-off.

### Markdown conventions the renderer understands

- `# Title` becomes the page header (dropped from the body; `--keep-h1` to keep it).
- `## Section` / `### 1. Step` (numeral → badge) / `#### Label` (→ kicker).
- A **bold-led** paragraph in the opening section renders as a callout.
- Tables get a horizontal scroll container below 560px.
- ```` ```mermaid ```` fences (optionally preceded by `<!-- diagram: name -->`) become figures.

### Verify before publishing (required)

```bash
node skills/markdown-to-branded-html/scripts/verify_branded_html.mjs <output.html> <screenshot-dir>
```
Headless Chromium at 1280 and 390 px: console errors, horizontal overflow, inline-SVG count, clipped
mermaid labels, `document.fonts` reports the brand font loaded, and the viewer opens / closes with the
SVG returned to the page. Then **look at the screenshots at 1:1** — a downscaled contact sheet hid a
heading colour that read as white on 2026-09-03.

### Keep it generated

The page is a derivative. Keep a small build wrapper next to the source markdown that calls this
script with the project's arguments (see `acme-health-main/docs/investigations/260716-billing-classification/build_prez_page.py`),
so a correction to the markdown or a `.mmd` is one rebuild and push away and the HTML is never
hand-edited. A rebuild must reproduce the committed page byte-for-byte apart from the build date.

## Files

```
scripts/
├── md_to_branded_html.py       # the renderer (python-markdown + Pillow; reads the composed template)
├── viewer.js                   # click-to-open zoom/pan viewer (shared, single owner)
├── mermaid_svg.mjs             # .mmd -> inline SVG via the vendored Chromium + mermaid 10 (native layout)
├── verify_branded_html.mjs     # headless verification + screenshots
└── assets/noto-sans-latin-300-700.woff2
```

Prerequisites: `python3 -m pip install markdown pillow`; node with the vendored
`team-lib/integrations/excalidraw-cli/node_modules` (Playwright Chromium + mermaid).

## Gotchas (all measured)

- **Mermaid 10 vs 11 wrap differently.** Hand `<br/>` breaks are tuned against the native renderer
  (no auto-wrap). Mermaid 11 (VS Code preview) auto-wraps at 200px *and* honours the breaks, orphaning
  words — put `%%{init: {"flowchart": {"wrappingWidth": 600}}}%%` after the `.mmd` frontmatter.
- **Never scope label resets to a container** — `svg foreignObject *{line-height:normal;box-sizing:content-box}`
  must be global or labels clip once the SVG is moved into the viewer.
- **A figure must be its own paragraph** in the markdown (blank line after the fence).
- **Verify the deploy by bytes**, not by status: poll until the served page hashes to the commit.
