---
name: markdown-to-branded-doc
description: "Converts markdown files to branded documents using pre-composed brand templates: .docx, new Google Docs (via gws CLI), and surgical section-level updates to existing Google Docs. Use when the user asks to render, format or brand a markdown file as a Word doc or Google Doc, to update one section of an existing branded Google Doc, or to build a branded HTML slide deck."
summary: "Renders markdown to branded documents using branded-template-v2 schema. Loads pre-composed templates from companies/{name}/brand/templates/{type}.json. Supports 7 document types across all brands. Includes update-gdoc-section.js for surgical edits to existing docs."
version: 4.9.1
last_updated: 2026-10-16
dependencies:
  - /_external/anthropics/skills/docx
listing: name-only
category: documents
---

# Markdown to Branded Doc

Convert Markdown documents to professionally formatted, branded documents. All styling comes from pre-composed branded templates — the renderer does no composition, no token resolution, no fallback chains.

## Rules that hold on every run

- **Never leave a finished Google Doc in Agent Templates.** Pass `--folder <folderId>` to the executor, and ask the user for the folder first. Template-based docs are copied, so without a folder they inherit the template's parent folder. Details: [Destination Folder](#destination-folder).
- **To change one section of an existing branded Google Doc, use `update-gdoc-section.js`.** A full re-render replaces the URL and discards reviewed formatting. Re-render only for structural changes or sections with tables. Details: [Surgical Section Updates](#surgical-section-updates-existing-docs).
- **A broken Mermaid diagram fails the build.** Fix the diagram, not the tool.
- **Every HTML slide deck passes the mobile-overflow audit before publishing.** See [reference/html-presentation.md](reference/html-presentation.md).

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
- `--brand` — Company slug: `your-brand`, `acme-health`, `contoso` (default: your-brand)
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
- `html-presentation` — Standalone HTML presentation (org-only, manual pathway — see below)

### Examples

```bash
# Legal document
node scripts/md-to-branded-doc.js ./msa.md ./msa.docx --brand your-brand --type doc-legal

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

### HTML document / artifact → use `markdown-to-branded-html`

For a branded HTML **document** (a report, walkthrough, handoff page, explainer — anything read
top-to-bottom, including prez.example.com document pages) use the sibling skill
`skills/markdown-to-branded-html/` with the composed `html-document` template. It is the default
format for branded HTML artifacts. The section below is the **slide deck**
pathway only.

### HTML Presentation (manual pathway)

Slide decks are built by hand from a brand template, not by the CLI (`--type html-presentation` is not supported yet). Read [reference/html-presentation.md](reference/html-presentation.md) before building one: it has the template, the substitution recipe, the slide components and the required mobile audit.

### Surgical Section Updates (existing docs)

When a branded Google Doc is already in place and only one section needs to change, **prefer `update-gdoc-section.js` over regenerating the whole doc**. Surgical updates preserve the URL, folder placement, header/footer, page numbers, and every untouched section's formatting exactly as-is.

```bash
node skills/markdown-to-branded-doc/scripts/update-gdoc-section.js \
  <source.md> <doc-id> \
  --section "<exact heading text>" \
  [--brand your-brand] [--type doc-report] [--dry-run]
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

Page numbers use a template-based approach. A Google Doc template (`_your-brand-doc-template-pagenums`) has pre-configured footer with auto-updating page numbers and "different first page" enabled. The executor copies this template via `files.copy` instead of creating a blank doc.

- **Template ID:** `1ece9BQ7ouVm0Zg-YCxGaM0REjPuz_yl4q8f1oYLH2i4`
- **Location:** Your Org > Templates > Agent Templates

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
| brand letterhead | `YOUR_LETTERHEAD_TEMPLATE_DOC_ID` | No — your brand only | Brand-specific header (logo, address, contact info) |

### How Templates Are Used

- **doc-report, doc-report-cover, doc-legal** — Copied from the page-number template. Executor clears body, inserts content, adds brand-specific header with favicon.
- **doc-letterhead** — Copied from the brand's letterhead template. Executor clears body, inserts content. Header/footer preserved from template.

### Creating Templates for New Brands

Letterhead templates are created automatically by `compose-branded-template.js` when `clasp` is available. If clasp is not installed:

1. Copy the brand letterhead template in Google Drive
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
