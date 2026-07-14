# Visual Guide Specification

Create a polished, navigable guide that demonstrates the target brand while documenting it. (Adapted from a community-shared generate-brand-guide visual-spec; values-from-tokens rules are ours.)

## Page architecture

- Clear cover/overview, then Personality, Color, Typography, Logo, Voice, Applied Examples, Accessibility, and a provenance footer, as applicable — omit sections with no source data.
- Persistent or compact navigation on large screens and an accessible mobile alternative (sticky top bar, anchor links, or a collapsible menu).
- Semantic HTML, landmark elements, logical heading order, visible focus states, and a skip link.
- Each section must be useful in isolation: concise rules plus visual examples.

## Demonstrations

- Render color swatches with token path, name, hex value, role/usage, and contrast-safe text pairing. Group: core brand → semantic (text/background/border/link/status) → heading hierarchy → derivatives (tints/shades).
- Badge tokens whose `$source` is `derived` or `fallback` so readers know what was computed vs. brand-specified.
- Render the actual type hierarchy with real brand copy (company name, tagline, realistic sentences), showing family, weight, size per level.
- Show every logo variant on its correct field: `logo.full`/`logo.icon` on light, `logo.fullOnDark`/`logo.iconOnDark` on dark. Preserve aspect ratio; note minimum-size/clear-space rules only if the guidelines define them.
- Voice: present tone/perspective/formality/avoidance; side-by-side do/don't examples only when the guidelines supply them, never invented.
- Applied examples: 3–5 patterns driven by the brand's `preference.*` enums, using real company info from tokens. Candidates: document header + signature table, slide title/cover, social card, email header block, callout/admonition. Each pattern must visibly honor the enum values it demonstrates (e.g. `docs.tableHeaders: branded` → primary background + white bold header text).
- Accessibility: render the `accessibility.computed` pairs from tokens as a table or annotated swatch pairs with ratio + level; state the brand's target level and flag anything below it (e.g. AA-large-only accents).

## Implementation

- One self-contained HTML file with embedded CSS. Embed logos and small assets as data URIs.
- Define every color and font as a CSS custom property named after its token path (e.g. `--color-brand-primary`); use only these variables (or rgba()/gradients built from them) in rules. This is what makes validation and future templating tractable.
- Web fonts: link Google Fonts only for families present in `typography.font.*`, with the token fallback stack declared so the page degrades gracefully offline. No other external requests.
- Fluid type and spacing with sensible max-widths. No horizontal scrolling at narrow widths; wide content (tables, swatch grids) scrolls inside its own container.
- Print styles: remove navigation chrome, keep legibility, avoid splitting key examples across pages.
- Respect `prefers-reduced-motion`. Motion is optional garnish, never required to understand the guide.

## Visual standard

The page itself must follow the rules it describes. Take the design direction from the brand's own `preference.web.*` enums (theme, card style, animation, CTA style) and the Brand Personality narrative — a dark-glass brand gets a dark glassmorphism guide, a light editorial brand gets a light one. Composition, density, color balance, and examples should express the target brand, not a reusable template aesthetic. Sections documenting non-web patterns (documents, slides) may render "paper" panels in those patterns' own idiom inside the page.
