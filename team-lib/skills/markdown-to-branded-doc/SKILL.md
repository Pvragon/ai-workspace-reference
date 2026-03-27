---
name: markdown-to-branded-doc
description: "Convert markdown files to branded documents using pre-composed branded templates. Supports .docx and Google Docs (via gws CLI)."
summary: "Renders markdown to branded documents using branded-template-v2 schema. Loads pre-composed templates from companies/{name}/brand/templates/{type}.json. Supports 7 document types across all brands."
version: 4.0.0
last_updated: 2026-03-19
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
                                   → render-branded-gdoc.js → JSON plan → execute-gdoc-api.js → Google Doc
```

1. **Parser** (`lib/parser.js`): Parses markdown via `marked.lexer()` into a format-agnostic IR
2. **Brand Loader** (`lib/brand-loader.js`): Loads pre-composed template from `context/indexed/companies/{brand}/brand/templates/{type}.json`
3. **DOCX Renderer** (`render-branded-docx.js`): Maps IR to docx library objects using template values
4. **Google Docs Renderer** (`render-branded-gdoc.js`): Maps IR to a JSON render plan (v2.4)
5. **Google Docs Executor** (`execute-gdoc-api.js`): Executes render plan via gws CLI

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
- `--brand` — Company slug: `pvragon`, `acme-corp`, `globex` (default: pvragon)
- `--type` — Document type (default: doc-report)
- `--format` — Output format: `docx` or `gdoc` (default: docx)
- `--list-brands` — List available brands
- `--list-types` — List available document types for a brand

**Document types:**
- `doc-report` — Standard branded report with TOC
- `doc-report-cover` — Report with dedicated cover page
- `doc-letterhead` — Formal correspondence, no page numbers
- `doc-legal` — Contracts, MSAs, SOWs — suppressed branding, 10pt, legal conventions
- `slides-informational` — Content-dense slides (read-oriented)
- `slides-formal` — Presentation slides (present-oriented)
- `html-presentation` — Standalone HTML presentation

### Examples

```bash
# Pvragon legal document
node scripts/md-to-branded-doc.js ./msa.md ./msa.docx --brand pvragon --type doc-legal

# Acme Corp report as Google Doc
node scripts/md-to-branded-doc.js ./report.md ./plan.json --brand acme-corp --type doc-report --format gdoc
node scripts/execute-gdoc-api.js plan.json [--folder <driveFolder>]
```

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
├── md-to-branded-doc.js         # CLI entry point
├── render-branded-gdoc.js       # Google Docs renderer (plan generation)
├── render-branded-docx.js       # DOCX renderer
├── execute-gdoc-api.js          # Google Docs plan executor (gws CLI)
├── lib/
│   ├── parser.js                # Markdown → DocumentIR
│   └── brand-loader.js          # Loads composed templates from company context
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
