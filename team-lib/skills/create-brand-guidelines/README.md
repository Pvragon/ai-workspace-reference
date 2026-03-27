---
template: system-documentation
version: 1.0.0
summary: "Architecture overview for the design-token-driven branded content system. Explains how brand-guidelines.md, brand-tokens.json, content-type templates, and branded templates connect to produce consistent branded output across all content types."
created: 2026-03-14
last_updated: 2026-03-14
maintainer: pvragon
---

# Design-Token-Driven Branded Content System

## What This System Does

Produces branded content — documents, slides, HTML presentations, and more — that is visually consistent, repeatable, and requires zero manual formatting. A brand is defined once, and every piece of content produced for that brand looks right automatically.

## End-to-End Flow

```
                    BRAND SETUP
                    (one-time per brand, re-run on brand changes)

    Source materials              create-brand-guidelines skill
    (PDFs, websites,       →     (interactive: ingest, extract,
     style guides, logos)         report coverage, fill gaps)
                                         ↓
                              brand-guidelines.md
                              (human-readable, brand-owner-maintained,
                               structured markdown with token tables)
                                         ↓
                              parse-brand-guidelines.js
                              (extracts tokens, computes derivatives,
                               validates accessibility)
                                         ↓
                              brand-tokens.json
                              (W3C Design Tokens aligned, machine-readable,
                               fully resolved — never hand-edited)


                    TEMPLATE COMPOSITION
                    (one-time per brand × content-type, re-run on brand or template changes)

    compose-branded-template.js performs a cascading deep merge — topmost layer wins:

    ┌───────────────────────────────────────────────────────┐
    │ Layer 4: content-type override (doc-legal.json)       │
    │   Only what DIFFERS from base for this type.          │
    │   Sets values = strong opinion. Omits keys = defer.   │
    ├───────────────────────────────────────────────────────┤
    │ Layer 3: universal base (_base-doc.json)              │
    │   Formatting rules shared across all content types.   │
    │   Spacing, bullets, tables, page breaks.              │
    ├───────────────────────────────────────────────────────┤
    │ Layer 2: brand-tokens.json                            │
    │   Brand identity (colors, fonts, logos) +             │
    │   brand preferences (tableHeaders, lineSpacing, etc.) │
    │   + computed derivatives (heading tints, shades).      │
    ├───────────────────────────────────────────────────────┤
    │ Layer 1: system defaults (in compose-branded-template.js)              │
    │   Final fallback for anything undefined above.        │
    └───────────────────────────────────────────────────────┘
                          ↓
              branded content-type template
              (fully resolved JSON — every value concrete,
               no token references, no merge logic.
               Stored in companies/{name}/brand/templates/)


                    CONTENT CREATION
                    (each time you produce a piece of content)

    input.md                branded content-type template
    (the actual content)    (the complete formatting spec)
           \                        /
            \                      /
             → rendering skill  ←
               (render-gdoc.js / render-docx.js /
                render-slides.js / render-html.js)
                      ↓
               Google Doc / .docx / PDF /
               Google Slides / HTML presentation
```

## The Four Artifacts

### 1. `brand-guidelines.md` — The Human-Readable Source of Truth

**What it is:** A structured markdown file with tables of token paths and values. Defines everything about a brand's visual identity and content presentation preferences.

**Who owns it:** The brand owner (marketing team, company owner, or designer) — maintained via the `create-brand-guidelines` skill.

**What it contains:**
- **Core identity** — colors (brand, text, background, border, link, status with light/med/dark triads), typography (fonts, weights), logos (light + dark variants with dimensions)
- **Company information** — name, legal name, address, contact details
- **Voice & tone** — attributes for content generation (tone, perspective, formality)
- **Heading hierarchy** — per-level heading colors (h1–h6) with fallback chain, plus strategy preferences for derived styles
- **Content presentation preferences** — enumerated choices per content type (documents, slides, HTML/web, social, advertising, long-form) that control how the brand is expressed in each format
- **Accessibility targets** — minimum contrast ratios (AA/AAA)

**What it does NOT contain:**
- Computed derivative colors (tints, shades) — those are generated
- Content-type formatting structure (heading sizes, page layout, bullet mechanics) — those live in content-type templates
- Per-content-type overrides of preferences — those are resolved during composition

**Key design principle:** Everything in this file is a **brand decision**, not a formatting decision. "Our primary color is #1E4958" is a brand decision. "H1 headings are 18pt" is a formatting decision that belongs in the content-type template.

### 2. `brand-tokens.json` — The Machine-Readable Derivative

**What it is:** A JSON file aligned to the W3C Design Tokens specification (2025.10), generated by `parse-brand-guidelines.js` from `brand-guidelines.md`. Never hand-edited.

**What it adds beyond brand-guidelines.md:**
- **W3C-structured tokens** — every color, font, weight, dimension wrapped in `{ "$value": "...", "$type": "...", "$description": "..." }` format
- **Computed derivatives** — tint/shade palette generated from core brand colors via HSL lightness adjustment (3 tint steps, 2 shade steps by default). These derivatives feed heading hierarchies, slide theme accents, HTML glow colors, etc.
- **Resolved heading colors** — if brand-guidelines specifies a `heading.colorStrategy` but leaves h4–h6 blank, the tokens file contains the computed values
- **Absolute logo paths** — relative paths from brand-guidelines resolved to absolute filesystem paths
- **Accessibility metadata** — computed contrast ratios for all color pairings, pass/fail flags against the brand's target level
- **Preference flags** — content presentation preferences passed through as-is for the composition layer to consume

**Why it exists separately from brand-guidelines.md:**
The guidelines file is optimized for humans (descriptive names, usage context, markdown tables). The tokens file is optimized for machines (structured JSON, zero interpretation, computed values pre-resolved). The parser bridges the gap — it runs once and produces a deterministic, complete representation that compose-branded-template.js and renderers can consume without ambiguity.

### 3. Content-Type Templates — The Formatting Structure

**What they are:** JSON files that define how a specific type of content is structured and formatted, independent of any brand. They live in the composition skill's `templates/` directory.

**Architecture: base + override**

```
_base-doc.json              Universal document formatting rules.
                            Line spacing, paragraph spacing, bullet behavior,
                            table mechanics, page break logic, HR style.
                            A universal change = one file edit.
                                    ↓ (deep merge)
doc-report.json             Only what DIFFERS from base for a report:
doc-legal.json              heading sizes, callout structure, TOC, cover page,
doc-letterhead.json         legal numbering, signature blocks, etc.
doc-report-cover.json
                                    ↓ (similarly)
_base-slides.json           Universal slide formatting rules.
                                    ↓ (deep merge)
slides-formal.json          Type-specific slide overrides.
slides-informational.json

html-presentation.json      Standalone (no base) — HTML is too different
                            from paginated content to share a base.
```

**How they interact with brand data — the cascading stack:**

Content-type templates don't reference brand tokens directly. Instead, compose-branded-template.js deep-merges the layers in a fixed order (system defaults → brand tokens → universal base → content-type override). The topmost layer that sets a value wins.

Content-type templates express opinions by **setting values** and defer by **omitting keys**:

```json
// doc-legal.json — SETS tableHeaders (strong opinion, overrides brand preference)
{
  "tables": {
    "headerStyle": "restrained"
  }
}

// doc-report.json — OMITS tableHeaders (defers to base → brand → system default)
{
  "tables": {
    // headerStyle not present — falls through to lower layers
  }
}
```

For structural values like heading font sizes, the content-type template always sets them (these are formatting decisions, not brand decisions):

```json
// doc-report.json
{
  "headings": {
    "h1": { "fontSize": 18 },
    "h2": { "fontSize": 14 },
    "h3": { "fontSize": 12 }
  }
}
```

The brand layer provides the colors and fonts. The content-type layer provides the sizes and spacing. compose-branded-template.js merges them into one flat structure where every value is concrete.

**What they contain:**
- Page/slide dimensions, margins, orientation
- Heading sizes and spacing (h1–h6) per content type
- Body text size, spacing, alignment defaults
- Table structure (cell padding, dense thresholds, overflow behavior)
- List/bullet mechanics (glyph style, indent per level, tiered spacing)
- Callout/admonition structure
- Page break logic (orphan detection, heading chain awareness)
- Header/footer layout
- Cover page layout (report-cover)
- Legal-specific features (numbering, signature blocks, confidentiality)
- Slide-specific features (slide types, transitions, footer)
- HTML-specific features (wave canvas, glassmorphism, components, navigation)

**What they do NOT contain:**
- Any concrete color, font, or logo value — always a `tokenRef`
- Any brand-specific decision — always deferred or defaulted

### 4. Branded Content-Type Templates — The Composed Output

**What they are:** Fully resolved JSON files produced by `compose-branded-template.js` — the merge of brand tokens + content-type template. One file per brand × content-type combination. Stored in `companies/{name}/brand/templates/`.

**Key properties:**
- **Fully concrete** — no `tokenRef` remaining, no merge logic, no fallback chains. Every value is a hex color, font name, pixel dimension, or boolean.
- **Renderer-ready** — the rendering skill reads one file and executes. Same input → same output, every time.
- **Inspectable** — you can open any branded template and see exactly what will be rendered. No hidden resolution.
- **Traceable** — every value came from either brand-tokens.json or the content-type template. The composition metadata records which source produced each value.

**Current content types (7):**
1. `doc-report` — Standard branded report (the workhorse)
2. `doc-report-cover` — Report with dedicated cover page
3. `doc-letterhead` — Formal correspondence, minimal formatting
4. `doc-legal` — Contracts, MSAs, SOWs, visually restrained
5. `slides-formal` — Presentation slides, designed to be presented (large fonts, transitions)
6. `slides-informational` — Content-dense slides, designed to be read (smaller fonts, no transitions)
7. `html-presentation` — Self-contained HTML slideshow (dark glassmorphism theme)

## Precedence Rules — Cascading Stack

Values resolve by stacking layers. The topmost layer that defines a value wins. compose-branded-template.js performs a multi-layer deep merge in this fixed order:

```
┌─────────────────────────────────┐
│  4. Content-type override       │  ← wins if present
│     (doc-legal.json)            │     e.g., legal sets tableHeaders: restrained
├─────────────────────────────────┤
│  3. Universal content defaults  │  ← wins if layer 4 is absent
│     (_base-doc.json)            │     e.g., base sets lineSpacing: 115
├─────────────────────────────────┤
│  2. Brand tokens                │  ← wins if layers 3-4 are absent
│     (brand-tokens.json)         │     e.g., brand sets primary color, tableHeaders pref
├─────────────────────────────────┤
│  1. System defaults             │  ← final fallback
│     (hardcoded in compose-branded-template.js)   │     e.g., bodyFontSize: 12, bodyAlignment: left
└─────────────────────────────────┘
```

**How it works in practice:**

Table headers for a **report**: `doc-report.json` doesn't set `tableHeaders` → `_base-doc.json` doesn't set it either → brand-tokens.json has `docs.tableHeaders: branded` → result: `branded`.

Table headers for a **legal doc**: `doc-legal.json` sets `tableHeaders: restrained` → that's the final value. Brand preference is irrelevant — the content-type override wins.

Heading h1 color: `doc-report.json` doesn't set a color → `_base-doc.json` doesn't either → brand-tokens.json has `color.heading.h1: 4E6F7C` → result: `#4E6F7C`.

**No special mechanism needed.** Content-type templates express opinions by setting values and stay silent by omitting keys. compose-branded-template.js is a straightforward deep merge — topmost non-null value wins. No `tokenRef`, no `typeDefault`, no deferral logic.

## Skills

### `create-brand-guidelines`

Produces `brand-guidelines.md` for a brand. Two modes:

- **Create mode** — ingest source materials (PDF brand decks, website URLs, style guide images, existing brand files), extract what can be determined automatically, report coverage, then walk the user through filling gaps interactively. Partial completion is fine — the system handles missing tokens gracefully.
- **Update mode** — read an existing `brand-guidelines.md`, show current coverage, accept new source materials or user input to fill gaps or make changes.

Outputs: `brand-guidelines.md` in the brand's directory.
Then runs: `parse-brand-guidelines.js` to generate `brand-tokens.json`.

### `compose-branded-template`

Produces branded content-type templates by merging brand tokens with content-type templates.

- Reads: `brand-tokens.json` + `_base-*.json` + content-type override
- Writes: fully resolved branded template to `companies/{name}/brand/templates/`
- Validates: no unresolved tokenRefs, all required values present, accessibility checks pass

### `markdown-to-branded-doc`

Renders content from markdown to a branded output format.

- Reads: input markdown + branded content-type template
- Writes: Google Doc / .docx / PDF / Google Slides / HTML
- Does NO composition — reads one file, renders

## Directory Structure

```
team-lib/
├── skills/
│   ├── create-brand-guidelines/
│   │   ├── SKILL.md
│   │   ├── README.md                      ← this file
│   │   ├── brand-guidelines-template.md   ← blank template
│   │   └── scripts/
│   │       └── parse-brand-guidelines.js        ← brand-guidelines.md → brand-tokens.json
│   │
│   ├── compose-branded-template/
│   │   ├── SKILL.md
│   │   ├── templates/                     ← content-type templates
│   │   │   ├── _base-doc.json
│   │   │   ├── _base-slides.json
│   │   │   ├── doc-report.json
│   │   │   ├── doc-report-cover.json
│   │   │   ├── doc-letterhead.json
│   │   │   ├── doc-legal.json
│   │   │   ├── slides-formal.json
│   │   │   ├── slides-informational.json
│   │   │   └── html-presentation.json
│   │   └── scripts/
│   │       └── compose-branded-template.js                 ← base + override + tokens → branded template
│   │
│   └── markdown-to-branded-doc/
│       ├── SKILL.md
│       └── scripts/
│           ├── md-to-branded-doc.js
│           ├── render-gdoc.js
│           ├── render-docx.js
│           └── lib/
│               ├── parser.js
│               └── brand-loader.js
│
├── context/indexed/
│   └── companies/
│       ├── pvragon/
│       │   ├── company.json
│       │   └── brand/
│       │       ├── brand-guidelines.md    ← SOURCE OF TRUTH (brand owner maintains)
│       │       ├── brand-tokens.json      ← GENERATED (never hand-edited)
│       │       ├── assets/                ← logos, favicons
│       │       └── templates/             ← branded templates (generated)
│       │           ├── doc-report.json
│       │           ├── doc-report-cover.json
│       │           ├── doc-letterhead.json
│       │           ├── doc-legal.json
│       │           ├── slides-formal.json
│       │           ├── slides-informational.json
│       │           └── html-presentation.json
│       ├── example-brand/
│       │   └── (same structure)
│       └── example-brand-2/
│           └── (same structure)
```

## Token Architecture

### Two-Layer Token System

| Layer | Format | Defined by | Covers | Interoperable? |
|-------|--------|-----------|--------|---------------|
| **Brand tokens** | W3C Design Tokens (2025.10) | Brand owner via brand-guidelines.md | Colors, typography, logos, voice, company info, content-type preferences | Yes — Style Dictionary, Tokens Studio, Pencil.dev |
| **Document tokens** | Our extension (document-tokens-v1) | Us, in content-type templates | Heading hierarchy, page layout, table mechanics, bullets, page breaks, headers/footers, callouts, cover pages, legal features, slide types, HTML components | No — novel layer, nothing else covers this |

### Derivative Color Generation

When `parse-brand-guidelines.js` generates `brand-tokens.json`, it computes a tint/shade palette from the core brand colors:

- **Method:** HSL lightness adjustment (deterministic, no interpretation)
- **Tint steps:** 3 (25%, 50%, 75% lighter)
- **Shade steps:** 2 (25%, 50% darker)
- **Applied to:** `color.brand.primary` and `color.brand.accent`

These derivatives are used for:
- Heading h4–h6 colors (when not explicitly defined)
- Slide theme accent palette (ACCENT1–6 mapping)
- HTML presentation glow/wave opacity values
- Background tints for hover states, active states

Brands that want precise control over derivatives can define them explicitly in the Extended Palette section of brand-guidelines.md — explicit values always override computed ones.

## Open Standards Alignment

| Component | Aligned to | Interoperability |
|-----------|-----------|-----------------|
| `brand-tokens.json` | W3C Design Tokens 2025.10 | Import/export with Style Dictionary, Tokens Studio, Pencil.dev |
| CSS/HTML variable output | Style Dictionary (Amazon) | Transform brand-tokens.json → CSS custom properties for web content types |
| Future Pencil.dev input | Pencil MCP tools | `get_variables`/`set_variables` for bidirectional sync |
| Document formatting tokens | Our extension (document-tokens-v1) | Novel — no standard exists for document-level formatting tokens |

## Strategic Context

The document generation market is ~$3B (2026), growing at 8.5% CAGR. Existing players focus on data merge or enterprise brand compliance — none connect design tokens to document production. The W3C design token ecosystem is mature for UI but stops entirely at the document boundary.

This system bridges that gap. The composition pipeline and document-tokens-v1 spec are candidates for open-source release as "Style Dictionary for Documents" once mature.
