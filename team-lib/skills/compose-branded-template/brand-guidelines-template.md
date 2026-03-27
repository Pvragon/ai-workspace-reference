# Brand Guidelines Template

## How to Fill In This Template

This template defines all the visual tokens your organization's documents, slides, and presentations will use. Fill in each table below with your brand's specific values.

**Instructions:**
1. Work through each section in order. Most sections have a "Usage" column explaining what the token controls.
2. Enter hex color values **without** the `#` prefix (e.g., `1E4958` not `#1E4958`).
3. Leave cells blank if you don't have a value — the rendering system will use sensible defaults or skip optional tokens.
4. Sections marked **(Optional)** can be left entirely empty if they don't apply to your brand.
5. For logo assets, provide file paths relative to the brand directory (e.g., `assets/logo.png`).
6. When you're done, save this file as `brand-guidelines.md` in your brand's directory.

---

## Colors

### Brand Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.brand.primary` | | | Main brand color — used for headers, accent bars, primary buttons |
| `color.brand.accent` | | | Secondary/highlight color — used for emphasis, calls-to-action |

### Text Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.text.default` | | | Primary body text color |
| `color.text.subtle` | | | Secondary text, captions, muted elements |
| `color.text.onPrimary` | | | Text placed on primary-colored backgrounds (usually white) |
| `color.text.onDark` | | | Text placed on dark backgrounds |

### Background Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.background.default` | | | Page/slide background (usually white) |
| `color.background.subtle` | | | Alternate table rows, subtle section backgrounds |
| `color.background.accent` | | | Callout boxes, highlighted areas |

### Heading Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.heading.primary` | | | H1/H3 heading color (leave blank to default to brand.primary) |
| `color.heading.accent` | | | H2 heading color (leave blank to default to brand.accent) |

### Status Colors (Optional)

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.status.success` | | | Positive indicators, success text |
| `color.status.successBg` | | | Success callout/badge background |
| `color.status.warning` | | | Negative indicators, warning text |
| `color.status.warningBg` | | | Warning callout/badge background |

### Border Colors

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `color.border.default` | | | Table borders, dividers |
| `color.border.subtle` | | | Decorative rules, light separators |

---

## Typography

| Token | Value | Usage |
|-------|-------|-------|
| `typography.font.primary` | | Main font for all text (e.g., Noto Sans, Montserrat) |
| `typography.font.fallback` | | Used when primary font is unavailable (e.g., Arial) |
| `typography.font.monospace` | | Code snippets and monospaced text (default: Courier New) |
| `typography.weight.heading` | | Heading weight as a number (default: 700) |
| `typography.weight.body` | | Body text weight as a number (default: 400) |
| `typography.weight.emphasis` | | Bold/emphasis weight as a number (default: 700) |
| `typography.weight.light` | | Light/subtle weight as a number (default: 300) |

---

## Logo Assets

Provide file paths relative to the brand directory. Width and height are in pixels.

### Primary Logos (Light Backgrounds)

| Token | File | Width | Height | Usage |
|-------|------|-------|--------|-------|
| `logo.full` | | | | Primary logo for headers, title pages |
| `logo.icon` | | | | Small icon/favicon for footers, subsequent pages |

### Dark Background Logos (Optional)

| Token | File | Width | Height | Usage |
|-------|------|-------|--------|-------|
| `logo.fullOnDark` | | | | Primary logo for dark backgrounds |
| `logo.iconOnDark` | | | | Small icon for dark backgrounds |

---

## Voice & Tone (Optional)

These attributes guide content generation and copywriting, not visual rendering.

| Attribute | Value |
|-----------|-------|
| `voice.tone` | |
| `voice.perspective` | |
| `voice.formality` | |
| `voice.avoidance` | |

---

## Company Information

Used for letterheads, footers, and cover pages. Leave blank if not applicable.

| Field | Value |
|-------|-------|
| `company.name` | |
| `company.legalName` | |
| `company.address` | |
| `company.phone` | |
| `company.website` | |
| `company.email` | |
| `company.tagline` | |
