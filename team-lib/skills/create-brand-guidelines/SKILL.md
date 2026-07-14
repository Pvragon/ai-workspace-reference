---
name: create-brand-guidelines
description: "Create or update a brand-guidelines.md file for any brand — the single source of truth for all branded content generation."
summary: "Interactive skill that produces a structured brand-guidelines.md by ingesting source materials (style guides, PDFs, websites, logos), extracting brand tokens, validating coverage, and walking the user through gap-filling. Supports create mode (new brand) and update mode (existing brand). Outputs brand-guidelines.md and brand-tokens.json."
version: 1.3.0
template: skill-definition
created: 2026-03-16
last_updated: 2026-07-13
maintainer: pvragon
dependencies: [node]
tags: [branding, design-tokens, brand-guidelines, content-pipeline]
---

# Skill: Create Brand Guidelines

## When to Use

- Setting up a new brand for the first time
- Migrating an existing brand's visual identity into the standardized format
- Updating a brand's colors, typography, logos, or content preferences
- Onboarding a client brand from their PDF style guide, website, or design files
- Reviewing coverage gaps in an existing brand-guidelines.md

## Prerequisites

- Node.js available in the environment
- Access to the brand's source materials (any combination of):
  - Style guide images (PNG/PDF)
  - Brand deck / PDF guidelines
  - Website URL
  - Existing brand config files (JSON, YAML, CSS, Tailwind config)
  - Logo files (SVG/PNG)
  - Existing SKILL.md-format brand guidelines (legacy format)
- Write access to `team-lib/context/indexed/companies/{brand-name}/brand/`

## How It Works

```
Source materials              This skill (orchestration)
(PDFs, images, URLs,    →    Read/view materials, extract values,
 existing configs)            sample for user verification
                                      ↓
                             brand-guidelines-template.md
                             (blank template with all token paths)
                                      ↓
                             Populated brand-guidelines.md
                             (filled with extracted + user-provided values)
                                      ↓
                             parse-brand-guidelines.js --validate
                             (extract tokens, compute derivatives,
                              check accessibility, report coverage)
                                      ↓
                             brand-tokens.json
                             (W3C-aligned, machine-readable,
                              fully resolved — never hand-edited)
```

## Modes

### Create Mode

Start from scratch for a new brand. The agent:

1. Copies the blank template
2. Ingests any source materials the user provides
3. Extracts as many token values as possible
4. Samples 3-5 extracted values and presents them for user verification
5. If sample is confirmed accurate, applies all extracted values
6. Reports coverage (what's filled, what's missing, what's optional)
7. Walks the user through missing sections interactively
8. User can stop at any point — partial completion is fine
9. Runs parse-brand-guidelines.js to generate brand-tokens.json
10. Presents final coverage summary

### Update Mode

Revisit an existing brand-guidelines.md. The agent:

1. Reads the existing file
2. Runs parse-brand-guidelines.js --coverage to show current state
3. Accepts new source materials or user input
4. Samples any newly extracted values for verification
5. Applies changes
6. Re-runs parse-brand-guidelines.js to regenerate brand-tokens.json
7. Presents updated coverage summary

## Procedure

### Step 1: Determine mode and brand

Ask the user:
- **Which brand?** (determines the target directory: `team-lib/context/indexed/companies/{brand-name}/brand/`)
- **Create or update?** (if brand-guidelines.md already exists in the target directory, suggest update mode)

If the company directory doesn't exist, create the folder structure:

```bash
mkdir -p team-lib/context/indexed/companies/{brand-name}/brand/assets
```

### Step 2: Gather source materials

Ask the user for any available brand materials:
- Style guide images or PDFs
- Website URL
- Existing brand config files (JSON, CSS, Tailwind, legacy SKILL.md)
- Logo files
- Any other reference materials

Read/view each provided material using your multimodal capabilities. Do not use external extraction scripts — read the materials directly.

### Step 3: Extract token values

From the source materials, extract values for as many tokens as possible. Track gaps as you go — partial extraction is expected and handled in Step 7.

**Never infer a rule from one accidental implementation.** A color that appears once on one web page is not a brand color; a repeated pattern across materials is. When sources conflict (e.g., the website CSS disagrees with the PDF style guide), resolve explicitly in this order:

1. The user's designated source of truth (ask which, if conflict matters)
2. Recent approved strategy documents over live implementation
3. Live implementation over historical drafts
4. Repeated patterns over isolated examples

Record unresolved conflicts and present them to the user in Step 4 rather than silently picking one.

**Token mapping guide:** Source materials rarely use our token names. Use this mapping:

| Source material says | Maps to token |
|---------------------|---------------|
| Primary / main / brand color | `color.brand.primary` |
| Secondary / accent / highlight color | `color.brand.accent` |
| Third / tertiary / supporting color | `color.brand.tertiary` |
| Body / dark / default text | `color.text.default` |
| Muted / gray / secondary text | `color.text.subtle` |
| White text / text on brand color | `color.text.onPrimary` |
| Page / card / default background | `color.background.default` |
| Alternate / subtle / light background | `color.background.subtle` |
| Tinted / callout / highlight background | `color.background.accent` |
| Border / divider / rule color | `color.border.default` |
| Light border / separator | `color.border.subtle` |
| Link / hyperlink color | `color.link.default` |
| Heading font / display font | `typography.font.primary` |
| Body font (if different from heading) | `typography.font.secondary` |
| Code / mono font | `typography.font.monospace` |

**From style guide images/PDFs:**
- Color palette with hex values and names
- Font families and weight specifications
- Logo variants and usage rules
- Brand personality / visual identity description

**From websites:**
- CSS custom properties or computed styles for colors, fonts
- Logo images and placement patterns
- Link colors and hover states

**From existing configs:**
- Direct color/font mappings
- Any structured token data

**From legacy SKILL.md brand guidelines:**
- Color tables → map to new token dot-paths
- Typography sections → font families and weights
- Logo references → logo token paths
- Design patterns → content presentation preference enums + notes
- Brand personality descriptions → brand personality section

### Step 4: Verify extraction accuracy

Present a sample of 3-5 extracted values to the user for verification:

```
I extracted these values from your materials — can you confirm they're correct?

1. Primary color: #532BDA (Brand Purple) ← from style guide image
2. Font family: Inter ← from CSS/style guide
3. Accent color: #FF5455 (Secondary Red) ← from style guide image
4. Body weight: 400 (Regular) ← from typography spec
5. Dark text: #161129 ← from style guide image

Are these correct? (If yes, I'll apply all extracted values. If any are wrong, let me know which.)
```

If the sample is confirmed accurate, apply all extracted values to the template. If any are wrong, flag the source material as unreliable for that category and ask the user to provide correct values manually.

### Step 5: Populate the template

**Create mode:** Copy `brand-guidelines-template.md` from this skill's directory, fill in extracted values.

**Update mode:** Edit the existing brand-guidelines.md in place.

**Frontmatter:** Update the YAML frontmatter immediately:
- `summary:` → one-line description of this brand (e.g., "Meridian Analytics brand guidelines — data analytics platform with ocean blue + amber identity")
- `created:` / `last_updated:` → today's date
- `maintainer:` → keep as `pvragon` (or the brand owner if external)
- Leave `schema: brand-guidelines-v1` unchanged

Fill sections in this order:
1. Brand Personality (visual identity + color application rules)
2. Core Identity — Brand Colors (primary, accent, tertiary)
3. Core Identity — Text, Background, Border, Link, Status colors
4. Extended Palette
5. Typography (fonts + weights)
6. Logo Assets (core logos + variants + usage notes)
7. Company Information
8. Voice & Tone
9. Heading Hierarchy (colors + strategy)
10. Content Presentation Preferences (docs, slides, web, social, ads, longform)
11. Accessibility targets

For each section:
- Fill in extracted values
- Tag each filled value's **provenance** in the Usage column (the parser ignores parentheticals there, so this is free metadata):
  - *(no tag)* = **approved** — user-confirmed or from the designated source of truth
  - `(observed)` — consistently present in materials but never formally approved
  - `(proposed)` — your recommendation, awaiting user approval
  - `(inferred)` — filled by convention (e.g., `color.text.onPrimary` is almost always white)
- For fields that require brand owner input, leave the value blank and track as missing
- Once the user confirms an `(observed)`/`(proposed)`/`(inferred)` value, remove the tag — untagged means approved

**Heading Colors note:** The Fallback column in the heading table is *system documentation* — it shows what the parser uses when the Hex column is blank. Do not modify the Fallback column. If the brand specifies an explicit hex for a heading level, put it in the Hex column; the explicit value always wins over the fallback.

**Common case — single heading color:** If the brand wants all headings in the same color (e.g., all primary blue), you MUST explicitly fill h1, h2, AND h3 in the Hex column. The h2 fallback defaults to the accent color, so leaving h2 blank gives it the wrong color. Set the strategy to `primary-only` and fill h1-h3 with the primary hex.

**Template Metadata:** Leave `meta.coveragePercent`, `meta.tokenCount`, `meta.missingRequired`, and `meta.missingOptional` blank for now — these are filled in Step 10 after the parser runs.

### Step 6: Report coverage

Present an **agent-estimated** coverage summary to the user. This is your own count based on the sections you just filled — the authoritative parser numbers come later in Step 9.

```
Brand Guidelines Coverage (estimated): [Brand Name]

Sections complete:    8/11
Tokens filled:        ~45/67
Tokens inferred:      6 (marked in Usage column, verify when possible)
Tokens missing:       ~16

Missing required:
  - color.border.default
  - color.border.subtle
  - company.address
  - company.phone

Missing optional:
  - color.brand.tertiary
  - color.link.hover
  - color.link.visited
  - typography.font.secondary
  - [content-type preferences left at defaults]

Would you like to fill in any missing sections now, or save and continue later?
```

This estimate helps the user decide whether to continue filling gaps or move to validation. Exact numbers will be reported by the parser in Step 9.

### Step 7: Interactive gap-filling

For each missing section the user wants to complete:
- Ask focused questions specific to that section, one at a time — never dump a questionnaire
- Ask for **decisions, not information that can be inspected** — anything answerable from the source materials should have been extracted in Step 3
- Provide sensible defaults where applicable ("Most brands use left-aligned body text — want to keep that, or switch to justified?")
- When the user struggles with an abstract question, offer 2-3 concrete directions to pick from instead of rephrasing the abstraction
- Accept "skip" to move on
- Accept "done" to stop the interactive process entirely

### Step 8: Generate brand-tokens.json

Run the parser to generate the machine-readable token file:

```bash
node team-lib/skills/create-brand-guidelines/scripts/parse-brand-guidelines.js \
  --input team-lib/context/indexed/companies/{brand-name}/brand/brand-guidelines.md \
  --output team-lib/context/indexed/companies/{brand-name}/brand/brand-tokens.json
```

### Step 9: Validate and present results

Run validation first, then coverage. **Run these sequentially, not in parallel** — `--validate` exits with code 1 when contrast failures exist, which can cancel a parallel `--coverage` call.

```bash
node team-lib/skills/create-brand-guidelines/scripts/parse-brand-guidelines.js \
  --input team-lib/context/indexed/companies/{brand-name}/brand/brand-guidelines.md \
  --validate
```

```bash
node team-lib/skills/create-brand-guidelines/scripts/parse-brand-guidelines.js \
  --input team-lib/context/indexed/companies/{brand-name}/brand/brand-guidelines.md \
  --coverage
```

Note: `--validate` exit code 1 means contrast failures were found — this is a report, not a crash. Proceed to `--coverage` regardless.

Present the final summary:
- Token count and coverage percentage (from parser output)
- Accessibility check results (contrast ratios, pass/fail against target level)
- Derivative colors generated (read the `color.derivative` section of the JSON to report the count)
- Any warnings (e.g., accent color fails AA contrast on white)

**Contrast failures:** If any color combination fails the brand's target contrast level:
1. Report the specific failure (which foreground on which background, actual ratio vs required)
2. Note whether the failure applies to *all* text or only large text (AA-large = 3:1 is fine for headings/buttons)
3. Offer to suggest a darker/lighter accessible alternative if the user wants one
4. Do NOT auto-fix — contrast is a brand decision. Just inform.

### Step 10: Update metadata

After the parser has run, update the Template Metadata section at the bottom of brand-guidelines.md with the authoritative values:

| Field | Source |
|-------|--------|
| `meta.createdBy` | Already filled in Step 5 |
| `meta.createdDate` | Already filled in Step 5 |
| `meta.lastModifiedBy` | Agent name or "create-brand-guidelines skill" |
| `meta.lastModifiedDate` | Today's date |
| `meta.coveragePercent` | From parser `--coverage` output (e.g., `83.2`) |
| `meta.tokenCount` | From parser `--coverage` output, format as `N defined + M derived` (e.g., `79 defined + 18 derived`) |
| `meta.missingRequired` | Comma-separated list from parser, or `none` if all required tokens are present |
| `meta.missingOptional` | Comma-separated list from parser, or `none` if all optional tokens are present |

### Checkpoint

- [ ] brand-guidelines.md saved to `companies/{brand-name}/brand/`
- [ ] brand-tokens.json generated in same directory
- [ ] Coverage reported to user (authoritative parser numbers)
- [ ] Accessibility validated
- [ ] Contrast failures explained (if any)
- [ ] User informed of any missing required tokens
- [ ] Template Metadata section updated with parser results
- [ ] Handoff states which checks ran and any limitations honestly — list unresolved conflicts, `(observed)`/`(proposed)`/`(inferred)` values awaiting approval, and checks that did NOT run

**Follow-on:** to produce human-facing visual brand documentation from the tokens, run `generate-brand-guide-site` — it renders brand-tokens.json + the narrative sections of this file into a self-contained brand-guide.html.

## Template Reference

The blank template is at:
```
team-lib/skills/create-brand-guidelines/brand-guidelines-template.md
```

Schema version: `brand-guidelines-v1` (template v1.2.0)

### Template Sections

| Section | Contains | Parsed into tokens? |
|---------|---------|-------------------|
| Brand Personality | Visual identity description, color application rules | No — narrative guidance |
| Core Identity | Colors (brand, text, bg, border, link, status), extended palette | Yes |
| Typography | Font families, font weights | Yes |
| Logo Assets | Core logo tokens + additional variants table + usage notes | Core logos: yes. Variants/notes: no |
| Company Information | Name, legal name, address, contact | Yes |
| Voice & Tone | Tone, perspective, formality, avoidance | Yes |
| Heading Hierarchy | Per-level heading colors + strategy preferences | Yes |
| Content Presentation Preferences | Enumerated choices for 7 content types + free-text notes | Enums: yes. Notes: no |
| Accessibility | Contrast ratio targets | Yes |
| Template Metadata | Creation/modification tracking, coverage stats | Auto-filled |

## parse-brand-guidelines.js Reference

Located at: `team-lib/skills/create-brand-guidelines/scripts/parse-brand-guidelines.js`

### Usage

```bash
# Generate brand-tokens.json
node scripts/parse-brand-guidelines.js \
  --input path/to/brand-guidelines.md \
  --output path/to/brand-tokens.json

# Validate only (no output file)
node scripts/parse-brand-guidelines.js \
  --input path/to/brand-guidelines.md \
  --validate

# Coverage report only
node scripts/parse-brand-guidelines.js \
  --input path/to/brand-guidelines.md \
  --coverage
```

### What it does

1. Parses markdown tables to extract token/value pairs
2. Resolves heading color fallback chains (h3 → h1, etc.)
3. Computes derivative colors (HSL tint/shade from primary, accent, tertiary)
4. Computes heading h4-h6 colors from strategy when not explicitly defined
5. Resolves logo paths to absolute filesystem paths
6. Converts preference strings to native JSON types (booleans, numbers)
7. Computes accessibility contrast ratios for all foreground/background pairings
8. Outputs W3C Design Tokens-aligned JSON (brand-tokens-v1 schema)

### Output schema

See `my-lib/runtime/.tmp/260314-brand-tokens-schema-draft.json` for the full schema with Pvragon example values. Key sections:

- `$schema` + `$generated` — metadata and coverage stats
- `color.*` — all colors in W3C `{ "$value", "$type", "$description" }` format
- `typography.*` — fonts and weights in W3C format
- `logo.*` — file paths, absolute paths, dimensions
- `company.*` — plain strings
- `voice.*` — plain strings
- `preference.*` — native JSON types (string/number/boolean)
- `accessibility.*` — targets + computed contrast ratios

## Notes

- **Partial completion is expected.** Not every brand will have all tokens defined. The system handles missing tokens via the cascading stack (content-type defaults → system defaults).
- **Narrative sections are valuable.** Brand Personality, Color Application Rules, Logo Usage Notes, and per-content-type Notes are not parsed into tokens but serve LLMs and designers reading the file directly. Encourage users to fill these in.
- **Extended Palette overrides derivatives.** If a brand explicitly defines a light variant in Extended Palette (e.g., `color.extended.brandLight: F2EEFF`), it takes precedence over the computed tint of the primary color.
- **This skill replaced the legacy per-brand SKILL.md format** (the old `skills/brand-guidelines/` directory, now removed). Brand identity lives in `context/indexed/companies/{brand}/brand/brand-guidelines.md`.
