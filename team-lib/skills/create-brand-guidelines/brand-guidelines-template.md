---
template: brand-guidelines
version: 1.2.0
summary: "Brand guidelines template — structured markdown defining all visual, typographic, and behavioral tokens for a brand, with narrative guidance alongside structured data. Source of truth for brand-tokens.json generation. Filled via create-brand-guidelines skill."
created: 2026-03-14
last_updated: 2026-03-16
maintainer: pvragon
schema: brand-guidelines-v1
---

# Brand Guidelines: [Company Name]

> This file is the single source of truth for [Company Name]'s brand identity across all content types.
> It is maintained by the brand owner and parsed by `parse-brand-guidelines.js` to generate `brand-tokens.json`.
>
> **Coverage:** Tokens left blank use system defaults or are skipped. Run the coverage report
> (`parse-brand-guidelines.js --coverage`) to see what's defined vs. missing.

---

## Brand Personality

A short description of the brand's visual identity and overall feel. This is not parsed into tokens — it's narrative guidance for anyone (human or AI) creating content for this brand.

**Visual identity:**

**Color application rules:**

---

## Core Identity

### Brand Colors

The foundational colors that define the brand. Every other color in the system derives from or complements these.

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.brand.primary` | | | Main brand color — anchors headings, accent bars, primary UI elements |
| `color.brand.accent` | | | Secondary brand color — emphasis, calls-to-action, contrast elements |
| `color.brand.tertiary` | | | Optional third brand color — additional variety in charts, diagrams, multi-color layouts. Leave blank if the brand uses only two colors. |

### Text Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.text.default` | | | Primary body text |
| `color.text.subtle` | | | Secondary text, captions, muted labels |
| `color.text.onPrimary` | | | Text on primary-colored backgrounds (usually white) |
| `color.text.onDark` | | | Text on dark backgrounds |

### Background Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.background.default` | | | Page/slide/card background (usually white) |
| `color.background.subtle` | | | Alternate table rows, subtle section backgrounds |
| `color.background.accent` | | | Callout boxes, highlighted areas, info panels |

### Border Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.border.default` | | | Table borders, card edges, dividers |
| `color.border.subtle` | | | Decorative rules, light separators |

### Link Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.link.default` | | | Hyperlink text color |
| `color.link.hover` | | | Link hover state (web/HTML content types) |
| `color.link.visited` | | | Visited link color (web/HTML content types) |

### Status Colors

Status colors communicate meaning (success, warning, error, info). Each has a light/medium/dark triad for backgrounds, icons/accents, and text respectively.

#### Success

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.status.successLight` | | | Success callout/badge background |
| `color.status.successMed` | | | Success icons, accent elements |
| `color.status.successDark` | | | Success text, strong indicators |

#### Warning / Error

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.status.warningLight` | | | Warning callout/badge background |
| `color.status.warningMed` | | | Warning icons, accent elements |
| `color.status.warningDark` | | | Warning text, strong indicators |

### Extended Palette (Optional)

Additional brand-specific colors not covered above — intermediate neutrals, special-purpose tones, or colors from the brand's style guide that don't fit the semantic categories. Chart and data visualization palettes are derived automatically from brand colors (primary, accent, tertiary + computed tints/shades) and do not need to be listed here.

| Token | Name | Hex | Usage |
|-------|------|-----|-------|

> Add rows as needed. Use descriptive token names (e.g., `color.extended.lightTeal`).
> The parser accepts any `color.extended.*` token.
> If the brand has no extended colors, leave this table empty (header row only).

---

## Typography

### Font Families

| Token | Value | Usage |
|-------|-------|-------|
| `typography.font.primary` | | Primary font for headings and body text |
| `typography.font.secondary` | | Optional second font for contrast (e.g., display headings, pull quotes). Leave blank to use primary everywhere. |
| `typography.font.fallback` | | System fallback when primary/secondary unavailable (e.g., Arial, Helvetica) |
| `typography.font.monospace` | | Code snippets and technical content (default: Courier New) |

### Font Weights

Numeric values (100–900). Common: 300=Light, 400=Regular, 500=Medium, 600=SemiBold, 700=Bold, 900=Black.

| Token | Value | Usage |
|-------|-------|-------|
| `typography.weight.light` | | Light/subtle text, de-emphasized elements |
| `typography.weight.body` | | Standard body text |
| `typography.weight.medium` | | Semi-emphasized text, sub-labels |
| `typography.weight.heading` | | Section headings |
| `typography.weight.display` | | Titles, hero text, maximum emphasis |

---

## Logo Assets

Provide file paths relative to the brand's `assets/` directory. Width and height in pixels (optional — used as layout hints by renderers; leave blank if unknown).

### Core Logos

These four tokens are used by the rendering pipeline. At minimum, define `logo.full`.

| Token | File | Width | Height | Usage |
|-------|------|-------|--------|-------|
| `logo.full` | | | | Full logo with wordmark — headers, title/cover pages (light backgrounds) |
| `logo.icon` | | | | Icon/favicon only — footers, small placements, subsequent pages (light backgrounds) |
| `logo.fullOnDark` | | | | Full logo for dark backgrounds — dark slides, HTML presentations |
| `logo.iconOnDark` | | | | Icon for dark backgrounds |

### Additional Logo Variants (Optional)

Brands with multiple logo variants (stacked/horizontal layouts, monochrome colorways, etc.) can list them here. These are not parsed into tokens but are available for the create-brand-guidelines skill and rendering skills to reference.

| Filename | Layout | Background | Colorway | Notes |
|----------|--------|------------|----------|-------|
| | | | | |

> **Layout**: horizontal, stacked, icon-only
> **Background**: light, dark, any
> **Colorway**: full-color, monochrome, single-color (specify which)

### Logo Usage Notes

---

## Company Information

Used for letterheads, footers, cover pages, and anywhere the entity is formally identified.

| Field | Value |
|-------|-------|
| `company.name` | |
| `company.legalName` | |
| `company.tagline` | |
| `company.address` | |
| `company.phone` | |
| `company.email` | |
| `company.website` | |

---

## Voice & Tone

These attributes guide content generation, copywriting, and AI-authored text. They do not affect visual rendering.

| Attribute | Value |
|-----------|-------|
| `voice.tone` | |
| `voice.perspective` | |
| `voice.formality` | |
| `voice.avoidance` | |

---

## Heading Hierarchy

Defines how headings are styled across content types. The brand sets the **color strategy** and **weight progression** — content-type templates control sizes and spacing.

### Heading Colors

Heading colors can be explicitly defined per level, or the system will derive them from the color strategy and the core palette. **Fill in the Hex column only** — the Fallback column is read-only system documentation showing what the parser uses when Hex is blank.

| Token | Hex | Fallback (system default — do not edit) | Usage |
|-------|-----|------------------------------------------|-------|
| `color.heading.h1` | | `color.brand.primary` | H1 heading color |
| `color.heading.h2` | | `color.brand.accent` | H2 heading color |
| `color.heading.h3` | | `color.heading.h1` | H3 heading color |
| `color.heading.h4` | | derived from strategy | H4 heading color |
| `color.heading.h5` | | derived from strategy | H5 heading color |
| `color.heading.h6` | | derived from strategy | H6 heading color |

> **How it works:** If you provide a hex value, that exact color is used. If you leave Hex blank,
> the parser falls back to the value shown in the Fallback column (h1→primary, h2→accent, h3→h1).
> For h4–h6, the heading color strategy (below) determines the computed color.
> Brands that want all headings in one color should fill in h1–h3 explicitly and set the
> strategy to `primary-only`.

### Heading Style Strategy

These preferences control how the system derives heading styles when individual levels aren't explicitly defined.

| Preference | Value | Options |
|------------|-------|---------|
| `heading.colorStrategy` | | `alternating` — h1/h3/h5 primary, h2/h4/h6 accent; `primary-only` — all primary shades; `accent-only` — all accent shades; `gradient` — progressive lightening h1→h6 |
| `heading.weightProgression` | | `bold-to-italic` — bold→bold→bold→bold-italic→italic→italic; `bold-only` — all levels bold; `weight-fade` — display→heading→heading→medium→body→body |

---

## Content Presentation Preferences

These preferences control how the brand is expressed in specific content types. Each is an enumerated choice — no interpretation needed.

Values resolve via a cascading stack: content-type override → universal base → brand preference → system default. The brand preference set here applies unless a content-type template explicitly overrides it. For example, if you set `docs.tableHeaders = branded` here, reports will use branded headers — but the legal template may override this to `restrained` because that's a strong structural opinion for legal documents.

### Documents

Applies to reports, letterheads, legal documents, and other paginated content.

| Preference | Value | Options | Default |
|------------|-------|---------|---------|
| `docs.bodyFontSize` | | `10` / `11` / `12` | `12` |
| `docs.bodyAlignment` | | `left` / `justified` | `left` |
| `docs.lineSpacing` | | `100` / `115` / `120` / `150` | `115` |
| `docs.tableHeaders` | | `branded` — primary bg + white text; `restrained` — subtle bg + dark text; `none` — no special header styling | `branded` |
| `docs.alternatingRows` | | `yes` / `no` | `yes` |
| `docs.tableDensity` | | `standard` / `compact` | `standard` |
| `docs.accentOnLabels` | | `yes` — bold labels use accent color; `no` — labels use default text color | `yes` |
| `docs.decorativeRules` | | `yes` / `no` — horizontal rules between major sections | `yes` |
| `docs.callouts` | | `yes` / `no` — callout/admonition boxes | `yes` |
| `docs.tocDefault` | | `yes` / `no` — include table of contents by default | `no` |

**Document notes:**

### Slides

Applies to formal presentations, informational decks, and pitch materials.

| Preference | Value | Options | Default |
|------------|-------|---------|---------|
| `slides.titleBackground` | | `primary` / `dark` / `white` / `accent` | `primary` |
| `slides.contentBackground` | | `white` / `light` / `dark` | `white` |
| `slides.closingBackground` | | `primary` / `dark` / `accent` | `primary` |
| `slides.logoProminence` | | `prominent` (60%) / `subtle` (30%) / `hidden` | `subtle` |
| `slides.bulletMarker` | | `accent` / `primary` / `neutral` | `accent` |
| `slides.accentStripe` | | `yes` / `no` — colored edge stripe on content slides | `yes` |
| `slides.footerContent` | | `numbers-only` / `numbers-and-company` / `none` | `numbers-and-company` |

**Slide notes:**

### HTML / Web

Applies to HTML presentations, landing pages, email templates, and web-based content.

| Preference | Value | Options | Default |
|------------|-------|---------|---------|
| `web.theme` | | `dark-glass` — dark glassmorphism; `dark-flat` — dark solid; `light` — light backgrounds; `branded` — primary dominant | `dark-glass` |
| `web.animation` | | `waves` — animated wave canvas; `subtle` — minimal movement; `none` — static | `waves` |
| `web.cardStyle` | | `glassmorphism` / `flat` / `bordered` | `glassmorphism` |
| `web.interiorGlows` | | `yes` / `no` — ambient brand-colored light effects | `yes` |
| `web.ctaStyle` | | `gradient` / `solid` / `outline` | `gradient` |

**Web notes:**

### Social Media

Applies to social graphics, post images, story templates, and profile assets.

| Preference | Value | Options | Default |
|------------|-------|---------|---------|
| `social.colorIntensity` | | `full` / `muted` / `vibrant` | `full` |
| `social.logoPlacement` | | `corner` / `center` / `watermark` | `corner` |
| `social.textOverlay` | | `dark-on-light` / `light-on-dark` / `brand-on-white` | `light-on-dark` |

**Social notes:**

### Advertising

Applies to display ads, banner creatives, and promotional materials.

| Preference | Value | Options | Default |
|------------|-------|---------|---------|
| `ads.ctaStyle` | | `bold` / `subtle` | `bold` |
| `ads.backgroundUsage` | | `photo` / `solid` / `gradient` / `brand-pattern` | `solid` |
| `ads.borderTreatment` | | `none` / `subtle` / `branded` | `none` |

**Advertising notes:**

### Long-Form / Editorial

Applies to whitepapers, case studies, ebooks, and extended written content.

| Preference | Value | Options | Default |
|------------|-------|---------|---------|
| `longform.pullQuotes` | | `accent-border` / `large-italic` / `boxed` | `accent-border` |
| `longform.footnoteStyle` | | `inline` / `endnotes` / `sidenotes` | `endnotes` |
| `longform.dropCaps` | | `yes` / `no` | `no` |
| `longform.chapterStyle` | | `page-break` / `continuous` | `page-break` |

**Long-form notes:**

---

## Accessibility

Minimum contrast ratios the brand commits to. Validated during token generation — the system warns if any color combination fails to meet the specified standard.

| Preference | Value | Options | Default |
|------------|-------|---------|---------|
| `a11y.textContrast` | | `AA` (4.5:1 normal, 3:1 large) / `AAA` (7:1 normal, 4.5:1 large) / `none` | `AA` |
| `a11y.uiContrast` | | `AA` (3:1) / `AAA` (4.5:1) / `none` | `AA` |

---

## Template Metadata

Filled by the `create-brand-guidelines` skill. `createdBy` and `createdDate` are set during Step 5 (template population). `coveragePercent`, `tokenCount`, and missing-token fields are updated in Step 10 after the parser runs.

| Field | Value |
|-------|-------|
| `meta.createdBy` | |
| `meta.createdDate` | |
| `meta.lastModifiedBy` | |
| `meta.lastModifiedDate` | |
| `meta.coveragePercent` | |
| `meta.tokenCount` | |
| `meta.missingRequired` | |
| `meta.missingOptional` | |
