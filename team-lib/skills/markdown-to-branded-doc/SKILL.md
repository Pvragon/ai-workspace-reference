---
name: markdown-to-branded-doc
description: "Convert markdown files to branded documents using pre-composed branded templates. Supports .docx, Google Docs (via gws CLI), and surgical section-level updates to existing Google Docs."
summary: "Renders markdown to branded documents using branded-template-v2 schema. Loads pre-composed templates from companies/{name}/brand/templates/{type}.json. Supports 7 document types across all brands. Includes update-gdoc-section.js for surgical edits to existing docs."
version: 4.8.0
last_updated: 2026-07-15
dependencies:
  - /_external/anthropics/skills/docx
---

# Markdown to Branded Doc

Convert Markdown documents to professionally formatted, branded documents. All styling comes from pre-composed branded templates — the renderer does no composition, no token resolution, no fallback chains.

## When to Use

- **docx format:** Client deliverables as Word files, offline sharing, email attachments
- **gdoc format:** Collaborative documents, shared Google Drive folders, documents needing comments/suggestions

## How It Works

```
Markdown → parser.js → DocumentIR → render-branded-docx.js → .docx file
                                   → render-branded-gdoc.js → JSON plan → execute-gdoc-api.js → new Google Doc
                                                                        → update-gdoc-section.js → existing Google Doc (surgical)
```

1. **Parser** (`lib/parser.js`): Parses markdown via `marked.lexer()` into a format-agnostic IR
2. **Brand Loader** (`lib/brand-loader.js`): Loads pre-composed template from `context/indexed/companies/{brand}/brand/templates/{type}.json`
3. **DOCX Renderer** (`render-branded-docx.js`): Maps IR to docx library objects using template values
4. **Google Docs Renderer** (`render-branded-gdoc.js`): Maps IR to a JSON render plan (v2.4)
5. **Google Docs Executor** (`execute-gdoc-api.js`): Executes a full render plan via gws CLI, creating a new doc
6. **Surgical Section Updater** (`update-gdoc-section.js`): Edits a single section of an existing Google Doc in place, preserving URL and untouched sections

## Usage

### Prerequisites

**Node dependencies:**
```bash
cd skills/markdown-to-branded-doc/scripts
npm install
```

**System dependencies:**

- **`gws` CLI** — Required for Google Docs output (`--format gdoc`). Handles OAuth and all Google API calls.
  - Install: `npm install -g @anthropic/gws` (or follow [gws setup docs](https://github.com/anthropics/gws))
  - Auth: Run `gws auth login` once to configure Google credentials for your workspace account
  - Verify: `gws docs list --limit 1` should return a document without errors
  - Not needed for `.docx` output — only required when using `--format gdoc` or running `execute-gdoc-api.js`

- **`pdftotext`** — Required for PDF-based orphan detection (heading placement optimization). Silently skipped if not installed — documents render correctly but orphan headings won't be detected.
  - Linux: `sudo apt install poppler-utils`
  - macOS: `brew install poppler`
  - Verify: `pdftotext -v` should print version info

### CLI

```bash
node scripts/md-to-branded-doc.js <input.md> <output> [--brand <brand>] [--type <type>] [--format docx|gdoc]
```

**Options:**
- `--brand` — Company slug: `pvragon`, `acme-health`, `contoso` (default: pvragon)
- `--type` — Document type (default: doc-report)
- `--format` — Output format: `docx` or `gdoc` (default: docx)
- `--render-metadata-table` — Render the YAML frontmatter as a metadata table at the top of the document. **Off by default** (added in v4.3.0) — most agent-authored markdown carries internal workspace bookkeeping in frontmatter (template/version/maintainer/created/last_updated) that should not appear in the rendered doc. Alternatively, set `_render_metadata_table: true` in the frontmatter itself to opt in per-document.
- `--no-excalidraw` — Opt OUT of Mermaid→Excalidraw diagram rendering (see Diagrams below). Default is **on**.
- `--mermaid-format svg|png` — Diagram image format (default: `png`).
- `--list-brands` — List available brands
- `--list-types` — List available document types for a brand

**Document types:**
- `doc-report` — Standard branded report with TOC
- `doc-report-cover` — Report with dedicated cover page
- `doc-letterhead` — Formal correspondence, no page numbers
- `doc-legal` — Contracts, MSAs, SOWs — suppressed branding, 10pt, legal conventions
- `slides-informational` — Content-dense slides (read-oriented)
- `slides-formal` — Presentation slides (present-oriented)
- `html-presentation` — Standalone HTML presentation (Pvragon-only, manual pathway — see below)

### Examples

```bash
# Pvragon legal document
node scripts/md-to-branded-doc.js ./msa.md ./msa.docx --brand pvragon --type doc-legal

# Acme Health report as Google Doc
node scripts/md-to-branded-doc.js ./report.md ./plan.json --brand acme-health --type doc-report --format gdoc
node scripts/execute-gdoc-api.js plan.json [--folder <driveFolder>]
```

### Diagrams (Mermaid → Excalidraw)

**Default-on, optional.** Any ` ```mermaid ` fenced code block in the markdown is
rendered to a hand-drawn **Excalidraw** image and embedded, via the
[[mermaid-to-excalidraw]] skill's engine (`excalidraw-cli`). Author diagrams as
plain Mermaid in the doc; iterate the *logic* in Mermaid, then just render the doc.

```markdown
​```mermaid
flowchart LR
  A[Write markdown] --> B[mermaid fence] --> C[Excalidraw image]
​```
```

- **Opt out** with `--no-excalidraw` (leaves the fence as raw text).
- All diagrams render in one headless-Chromium launch (amortized). A broken
  Mermaid diagram **fails the build** (fix the diagram, not the tool).
- **Diagrams are centered by default.**
- **Target support:** `docx` (local embed) and `gdoc` (upload-to-Drive →
  `insertInlineImage` → centered; the temp Drive upload is auto-trashed after the
  copy is embedded) both embed diagrams today — verified end-to-end.
  **`gslides` does NOT embed body images yet** — the pipeline renders the
  diagrams and prints a loud warning, but they won't appear in slides output until
  that renderer gets the same treatment. Follow-up.

### HTML Presentation (Pvragon, manual pathway)

The full brand-flexible HTML presentation pipeline is **not yet built** — see backlog `260319-html-presentation-skill.md` for the planned mood-skin + layout-primitives architecture. Until that lands, the working approach is to copy the Pvragon-specific hardcoded template, substitute placeholders, and embed the logos as base64 data URIs. The CLI flow (`md-to-branded-doc.js --type html-presentation`) does **not** support this yet.

**Template:** `team-lib/context/indexed/companies/pvragon/brand/assets/templates/html-presentation.html` — standalone file, dark glassmorphism aesthetic, animated wave canvas, keyboard navigation, progress bar. **Mobile-responsive since v2 (2026-07-09):** touch-swipe slide navigation, `dvh`-based card sizing (mobile URL-bar safe), `justify-content: safe center` on slides (overflowing content scrolls from the top instead of clipping — never remove the `safe` keyword), a dedicated phone-portrait regime (≤600px: near-full-viewport card, fluid `clamp()` type, diagram nodes become horizontal icon|title|desc rows, equations wrap as pill rows instead of stacking), and a phone-landscape regime covering every component (incl. `flow-visual` and the inline-styled 3rem slide-top icons via `!important`). Also ships a favicon `<link>` (was missing pre-v2).

**Output location:** `projects/presentations/pvragon/<human-friendly-slug>.html` (no date prefix; published at `prez.prgn.ai/pvragon/<slug>`).

**Reference design:** `projects/presentations/pvragon/ai-workspace-intro.html` — the canonical Pvragon HTML presentation; mirror its slide-component patterns, density, and tone.

**Latest worked example:** `projects/presentations/pvragon/portable-agent-package.html` (built 2026-04-29, build script at `my-lib/runtime/.tmp/260429-build-portable-agent-deck.py` — usable as a copy-paste starting point for the substitution flow).

#### Substitution recipe

1. Copy the template to the output path
2. Strip the leading `<!-- Pvragon Branded HTML Presentation Template ... -->` usage-comment block
3. Replace `__TITLE__` (h1 + `<title>` tag — strip HTML for the title tag), `__SUBTITLE__`
4. Replace example slides 2-4 with custom content (the template ships with 4 slides; add more by inserting additional `<div class="slide">` blocks before the navigation comment)
5. Strip the inter-slide `<!-- SLIDE N: ... -->` scaffolding comments after replacement (they're misleading once the example content is gone)
6. Update the static `<div class="slide-counter">1 / 4</div>` to reflect the real slide count (the JS overrides on init, but the static value should still be accurate)
7. Base64-embed `__LOGO_DATA_URI__` and `__FAVICON_DATA_URI__` from `team-lib/context/indexed/companies/pvragon/brand/assets/PV_Logo_onDark.png` and `PV_fav_onDark.png` — **do this AFTER slide insertion** so any new slides referencing `__LOGO_DATA_URI__` (e.g., a closing-slide logo header) also resolve

#### Slide structure rules

- **Slide 1 (title)** — `<img class="logo-header">` + `<h1>` with `<span class="accent">` for orange emphasis + `<p class="subtitle">`. No leading icon.
- **Content slides (middle)** — `<h2>` opens the slide (use `<span class="highlight">` for orange emphasis inline). Don't open content slides with a giant decorative icon — that's example-template scaffolding, not the established design language.
- **Closing slide (CTA)** — `<img class="logo-header">` + `<h2>` + body + `<div class="cta-container"><a class="cta-btn">`. The corner logo auto-hides on the first and last slides via the embedded JS.
- **Content density** — keep bullets to 3-5 per slide, ~1 line each. The slide card has firm 4.5rem top/bottom padding (content-safe-zone); overflow scrolls but reads poorly.

#### Component vocabulary (use these, not inline styles)

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

#### Embedding diagrams (Mermaid → Excalidraw)

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

#### Mobile verification (required before publishing)

Every new deck MUST pass `team-lib/skills/mobile-overflow-audit` before pushing:

```bash
node skills/mobile-overflow-audit/scripts/audit.js "file://<abs-path-to-deck>.html" --viewport 844x390   # phone landscape
node skills/mobile-overflow-audit/scripts/audit.js "file://<abs-path-to-deck>.html" --viewport 390x844   # phone portrait
```

Target `worstOverflow` ≤ 5px on both. If a slide still overflows after the template's responsive rules apply, **trim that slide's content** (shorten a paragraph, drop a bullet) rather than adding per-deck CSS — the template rules are the shared fix; content density is the per-deck fix. 568x320 (iPhone SE landscape) is allowed to scroll — `safe center` makes the scroll reach all content.

### Surgical Section Updates (existing docs)

When a branded Google Doc is already in place and only one section needs to change, **prefer `update-gdoc-section.js` over regenerating the whole doc**. Surgical updates preserve the URL, folder placement, header/footer, page numbers, and every untouched section's formatting exactly as-is.

```bash
node skills/markdown-to-branded-doc/scripts/update-gdoc-section.js \
  <source.md> <doc-id> \
  --section "<exact heading text>" \
  [--brand pvragon] [--type doc-report] [--dry-run]
```

**How it works:**
1. Extracts the named section from the source markdown (heading + content up to next same-or-higher heading).
2. Renders that section alone via the existing gdoc pipeline → mini render plan.
3. Fetches the existing doc, finds the section's range by matching heading text + paragraph style + the known-boundary-headings set from the source markdown (disambiguates real headings from body paragraphs that may have mis-inherited heading style).
4. Deletes the old range, inserts new content, resets the inserted range to NORMAL_TEXT baseline (so heading styles don't leak), then applies the mini-plan's formatting requests and native bullets with the correct index offset.
5. Never touches header/footer, page numbers, orphan detection, or any other section.

**Limitations:**
- Sections containing tables are not yet supported (warning issued; fall back to full re-render).
- Heading text must match between source markdown and existing doc (case-sensitive, exact).
- Orphan detection is NOT re-run — other sections' pagination is unchanged.
- The `--dry-run` flag shows the planned edits without modifying the doc.

**When to use surgical update vs. full re-render:**
- Surgical: single-section edits, polished docs that have been reviewed/shared, preserving the URL matters.
- Full re-render: structural changes (adding/removing sections), format changes, new brand tokens, or when the section contains a table.

### Destination Folder

Template-based docs (letterhead, page-number) are created via `drive.files.copy`, which makes them inherit the template's parent folder — Agent Templates. **Finished documents must never land in Agent Templates**; that folder is only for template sources.

- **Always** pass `--folder <folderId>` to place the doc in a project-specific Drive folder. Ask the user for the right folder before running the executor.
- If no `--folder` is given, the executor automatically moves the doc to Drive root as a fallback and prints a tip. This keeps Agent Templates clean but means the user has to find the doc at the root.

## Google Docs Pipeline

The executor handles everything automatically:

1. Creates the Google Doc (from page-number template when enabled)
2. Inserts all text content
3. Applies native bullets
4. Applies all formatting in batched `batchUpdate` calls
5. Inserts tables (replacing `[TABLE_N]` placeholders), optimizes column widths
6. Inserts keyword page breaks (Appendix, Exhibit, Schedule, Signature Block)
7. Sets header with favicon (pages 2+), inserts full logo on page 1 body
8. Runs PDF-based orphan detection (when enabled)

### Page Numbers

Page numbers use a template-based approach. A Google Doc template (`_pvragon-doc-template-pagenums`) has pre-configured footer with auto-updating page numbers and "different first page" enabled. The executor copies this template via `files.copy` instead of creating a blank doc.

- **Template ID:** `1ece9BQ7ouVm0Zg-YCxGaM0REjPuz_yl4q8f1oYLH2i4`
- **Location:** Pvragon LLC > Templates > Agent Templates

Page numbers are enabled per template type via `headerFooter.footer.pageNumbers`. Legal and report types have page numbers; letterhead does not.

### Header/Logo Strategy

The Google Docs API doesn't support creating first-page-only headers. Workaround:

- **Pages 2+:** Favicon/icon in the DEFAULT header (via `useFirstPageHeaderFooter` which hides it on page 1)
- **Page 1:** Full text logo inserted as an inline image at the top of the document body (right-aligned, 75% scale)

### Page Breaks

**Keyword-triggered** (all doc types): Visible `insertPageBreak` before headings starting with Appendix, Exhibit, Schedule, or Signature Block.

**Orphan detection** (when enabled): After all content is finalized, exports the document as PDF and cross-references page boundaries with the Docs API heading list. Headings near the bottom of a page with insufficient content after them get a visible page break inserted before them. Runs iteratively until no orphans remain.

- Uses `pdftotext` for page boundary extraction (accurate positions)
- Uses Docs API `namedStyleType` for heading identification (accurate semantics)
- No height estimation heuristics — zero false positives from body text

### Subtitle Detection

Paragraphs between the title and first section heading can be treated as subtitle/metadata (brand-colored, styled). This is controlled per template type via `renderOptions.subtitleDetection`:

- **Enabled:** doc-report, doc-report-cover
- **Disabled:** doc-legal, doc-letterhead, slides (default)

## Brand Template Schema (branded-template-v2)

The renderer reads a single pre-composed JSON file per brand × type. Key sections:

| Section | What it controls |
|---------|-----------------|
| `documentSettings` | Page mode, margins, font, font size, line spacing |
| `headings` | h1–h6 styling (color, size, spacing, bold, italic) |
| `bodyText` | Normal paragraph styling |
| `inlineStyles` | Bold labels, links, code font |
| `tables` | Header row, alternating rows, borders |
| `headerFooter` | Logo, page numbers, alignment |
| `renderOptions` | subtitleDetection |
| `pageBreaks` | orphanDetection |
| `themeColors` | Document theme palette |
| `titleBlock` | Title, subtitle, metadata styling |

Templates are generated by the `compose-branded-template` skill and stored at `context/indexed/companies/{brand}/brand/templates/{type}.json`.

## File Structure

```
scripts/
├── md-to-branded-doc.js         # CLI entry point (full-doc generation)
├── render-branded-gdoc.js       # Google Docs renderer (plan generation)
├── render-branded-docx.js       # DOCX renderer
├── execute-gdoc-api.js          # Google Docs plan executor (gws CLI, fresh doc creation)
├── update-gdoc-section.js       # Surgical section-level updater for existing Google Docs
├── lib/
│   ├── parser.js                # Markdown → DocumentIR
│   ├── brand-loader.js          # Loads composed templates from company context
│   └── orphan-detection.js      # PDF-based orphan heading detection
├── package.json
└── node_modules/
```

## Google Doc Starter Templates

The Google Docs pipeline uses pre-configured template documents to work around API limitations (page numbers, first-page headers). Template IDs are stored in each brand's composed templates under `googleDocTemplates`.

### Current Template IDs

| Template | ID | Shared? | Notes |
|----------|----|---------|-------|
| Page numbers | `1ece9BQ7ouVm0Zg-YCxGaM0REjPuz_yl4q8f1oYLH2i4` | Yes — all brands | Footer with auto-updating page numbers + "different first page" enabled |
| Pvragon letterhead | `1R_mBGvrZfOdAz8bkFWtr4Rn_rsfJqU0q0VClf7YDV-A` | No — Pvragon only | Brand-specific header (logo, address, contact info) |

### How Templates Are Used

- **doc-report, doc-report-cover, doc-legal** — Copied from the page-number template. Executor clears body, inserts content, adds brand-specific header with favicon.
- **doc-letterhead** — Copied from the brand's letterhead template. Executor clears body, inserts content. Header/footer preserved from template.

### Creating Templates for New Brands

Letterhead templates are created automatically by `compose-branded-template.js` when `clasp` is available. If clasp is not installed:

1. Copy the Pvragon letterhead template in Google Drive
2. Replace the logo, address, phone, email in the header
3. Update fonts to match the brand's primary font
4. Copy the new template's document ID from the URL
5. Run composition with: `--google-doc-templates '{"letterhead":"<new-id>"}'`

The page-number template is brand-independent and shared — no per-brand creation needed.

## API Limitations (Google Docs)

| Feature | Status | Workaround |
|---------|--------|------------|
| First-page header | Not supported by API | Full logo in body, favicon in DEFAULT header with `useFirstPageHeaderFooter` |
| Page numbers | No `insertAutoText` API | Template-based approach (copy from pre-configured template) |
| Named style definitions | No `updateNamedStyles` API | Could set via template doc or Apps Script (future) |
| Table alignment (centering) | No table-level alignment property | Left-aligned only via API. Apps Script can set alignment (future) |
| Page break elements | `insertPageBreak` ✓ | Working — visible, editable page breaks |
