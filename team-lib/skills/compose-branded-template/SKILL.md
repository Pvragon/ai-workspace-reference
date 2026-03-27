---
name: compose-branded-template
description: "Compose base + type-override templates with brand tokens to produce fully resolved branded templates. Deep merges base+override, resolves tokenRef dot-paths against brand-tokens.json, and applies brand preference fan-out."
summary: "Takes a brand name and template type, loads the base template and type override (via $extends), deep merges them, resolves all tokenRef dot-paths against brand-tokens.json, applies brand preferences (font size, table style, etc.), and writes the fully resolved branded template."
version: 2.1.0
created: 2026-03-14
last_updated: 2026-03-19
maintainer: pvragon
dependencies: []
---

# Compose Branded Template

Compose base + type-override templates with a brand's identity to produce fully resolved branded templates. The output templates are consumed directly by renderers (markdown-to-branded-doc, etc.) with no composition or token resolution at render time.

## When to Use

- When setting up a new brand and need all template types generated
- When brand-tokens.json changes (colors, fonts, logos) and templates need recomposition
- When adding a new document type template and need to compose it for existing brands
- Before rendering a document, if the branded template doesn't exist yet

## How It Works

```
_base-doc.json (universal formatting)
  + doc-report.json (thin type override, via $extends)
  = merged template (with tokenRef dot-paths)
  + brand-tokens.json (token values)
  + brand preferences (docs/slides fan-out)
  = branded template (fully resolved, renderer-ready)
```

1. Loads the type override from `templates/{type}.json`
2. If `$extends` is set, loads the base template and deep merges (override wins, null removes)
3. Resolves all `{ "tokenRef": "dot.path" }` objects against `brand-tokens.json`
4. Applies brand preference fan-out (e.g., `docs.bodyFontSize` → template font sizes). **Type-level overrides take precedence** — if a type template explicitly sets `documentSettings.defaultFontSize`, the brand preference won't override it (e.g., legal docs stay at 10pt even if the brand prefers 11pt).
5. Writes fully resolved output to `companies/{name}/brand/templates/{type}.json`

### Template Features (v2.1)

- **`renderOptions.subtitleDetection`** — Controls whether paragraphs between the title and first section heading are treated as subtitle/metadata. Default: `false` (off). Enabled only in doc-report and doc-report-cover.
- **`headerFooter.footer.pageNumbers`** — Controls whether the renderer enables page numbers. Default: `true`. Disabled for doc-letterhead.
- **`pageBreaks.orphanDetection`** — Controls whether the renderer runs PDF-based orphan heading detection. Default: `true`. Can be disabled per type.

## Usage

### Single Template

```bash
node skills/compose-branded-template/scripts/compose-branded-template.js --brand pvragon --type doc-report
```

### All Templates for a Brand

```bash
node skills/compose-branded-template/scripts/compose-branded-template.js --brand pvragon --all
```

### Dry Run (validate without writing)

```bash
node skills/compose-branded-template/scripts/compose-branded-template.js --brand pvragon --all --dry-run
```

## Template Types

| Type | Base | Description |
|------|------|-------------|
| `doc-report` | `_base-doc` | Standard branded report — headings, tables, bullets, callouts, TOC |
| `doc-report-cover` | `_base-doc` | Report with dedicated cover page |
| `doc-letterhead` | `_base-doc` | Formal correspondence — company info in header, simpler hierarchy |
| `doc-legal` | `_base-doc` | Contracts, MSAs — restrained colors, legal numbering, signatures |
| `slides-informational` | `_base-slides` | Content-heavy decks designed to be read |
| `slides-formal` | `_base-slides` | Presentation slides — larger fonts, speaker notes, transitions |
| `html-presentation` | *(standalone)* | Self-contained HTML slideshow with dark glassmorphism theme |

## Token Resolution

Templates use `tokenRef` dot-paths that map to brand-tokens.json:

```json
{ "tokenRef": "color.brand.primary" }           →  "1E4958"
{ "tokenRef": "typography.font.primary" }        →  "Noto Sans"
{ "tokenRef": "logo.full" }                      →  { "file": "...", "width": 150, ... }
{ "tokenRef": "company.name" }                   →  "Pvragon"
{ "tokenRef": "color.heading.h1" }               →  "1E4958"
{ "tokenRef": "color.status.successDark",
  "fallback": "color.brand.primary" }            →  tries successDark, falls back to primary
```

Colors are output as bare hex (no `#`) for Google Docs API compatibility.

## Brand Preference Fan-Out

Brand preferences from `brand-tokens.json > preference` map to specific template properties:

### Document Preferences
| Preference | Effect |
|------------|--------|
| `docs.bodyFontSize` | Sets `documentSettings.defaultFontSize` and `bodyText.normal.fontSize` |
| `docs.lineSpacing` | Sets `documentSettings.lineSpacing` and `bodyText.normal.lineSpacing` |
| `docs.tableHeaders = restrained` | Overrides table header to subtle bg + dark text |
| `docs.alternatingRows = no` | Sets `tables.alternateRowBackground` to null |
| `docs.accentOnLabels = no` | Changes `inlineStyles.boldLabel.color` to text.default |
| `docs.decorativeRules = no` | Sets `horizontalRule` to null |
| `docs.callouts = no` | Sets `callouts` to null |
| `docs.tocDefault = yes` | Sets `tocSupport.enabled` to true |

### Slide Preferences
| Preference | Effect |
|------------|--------|
| `slides.titleBackground` | Maps `primary/dark/white/accent` to resolved colors |
| `slides.bulletMarker` | Maps `accent/primary/neutral` to marker color |
| `slides.accentStripe = no` | Disables accent stripe |
| `slides.logoProminence` | Adjusts logo scale factor and opacity |
| `slides.footerContent` | Controls footer visibility and content |

## Deep Merge Semantics

- **Leaf values**: Override wins
- **null**: Override wins — explicitly removes the base value
- **Objects**: Recursive merge (override properties replace base at leaf level)
- **Arrays**: Override replaces entirely (no array merging)

## Output Schema

```json
{
  "$schema": "branded-template-v2",
  "composedFrom": {
    "template": "doc-report",
    "templateVersion": "2.0.0",
    "base": "_base-doc",
    "brand": "Pvragon",
    "brandSlug": "pvragon",
    "tokensVersion": "1.1.0",
    "tokensCoverage": 80,
    "composedAt": "2026-03-17T...",
    "composerVersion": "2.0.0"
  },
  "documentSettings": { ... },
  "headings": { "h1": { "color": "1E4958", ... }, ... },
  ...
}
```

## Adding a New Template Type

1. Create the type override in `templates/{type}.json` with `$extends` referencing the base
2. Only include properties that differ from the base
3. Use `tokenRef` dot-paths for all brand-variable values
4. Run `node scripts/compose-branded-template.js --brand <name> --type <type>` for each brand
5. Update the renderer to consume the new template type

## File Structure

```
skills/compose-branded-template/
├── SKILL.md                          ← this file
├── templates/
│   ├── _base-doc.json                ← universal document formatting
│   ├── _base-slides.json             ← universal slide formatting
│   ├── doc-report.json               ← thin override (titleBlock + TOC)
│   ├── doc-report-cover.json         ← thin override (+ coverPage)
│   ├── doc-letterhead.json           ← thin override (letter-specific)
│   ├── doc-legal.json                ← thin override (legal formatting)
│   ├── slides-formal.json            ← thin override (presentation)
│   ├── slides-informational.json     ← thin override (read-focused)
│   └── html-presentation.json        ← standalone (unique format)
└── scripts/
    └── compose-branded-template.js                    ← composition engine
```
