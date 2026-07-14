# Quality Checklist

Run before handoff. (Adapted from a community-shared generate-brand-guide quality checklist; evidence/governance items are handled upstream by our token pipeline, so this gate is presentation-focused.)

## Data fidelity

- Validator passes: every hex/rgb and font-family in the HTML exists in brand-tokens.json (or is a CSS generic); no external resources beyond approved Google Fonts; asset paths resolve.
- Color values, font names, and logo dimensions displayed as text match the tokens file exactly.
- Derived/fallback tokens are visibly badged, not presented as brand-specified.
- Narrative sections trace to brand-guidelines.md; nothing invented (no fabricated positioning, audience, usage rules, or do/don't examples).
- Contrast figures shown are the parser's computed values, not re-estimated.

## Visual system

- The page expresses this brand (per `preference.web.*` + Brand Personality), not a generic template look.
- Logo examples use the real assets, preserve aspect ratio, and sit on their correct light/dark fields.
- Type samples render in the brand font (or its declared fallback) — check the loaded font, don't assume.
- Applied examples conform to the preference enums they demonstrate.

## Page QA

- Navigation and internal anchors work.
- Keyboard focus is visible; reading order is logical; skip link present.
- Images have useful alt text; decorative images marked appropriately.
- Desktop (~1440px) and phone (~390px) layouts have no clipping or horizontal overflow.
- Print preview remains readable; navigation chrome removed.
- Browser console has no relevant errors.
- `prefers-reduced-motion` disables nonessential animation.

## Final handoff

- brand-guide.html delivered to `companies/{brand}/brand/`.
- State which checks ran (validator, widths inspected, checklist coverage) and any limitations honestly.
- Gaps discovered in the brand data are reported and routed to `create-brand-guidelines` update mode, not patched into the HTML.
