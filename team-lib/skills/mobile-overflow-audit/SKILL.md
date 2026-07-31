---
name: mobile-overflow-audit
description: "Audit a Pvragon HTML presentation for content-overflow on phone-landscape viewport, slide by slide. Returns a JSON report listing each slide's overflow in pixels plus the heading text and any custom component classes detected. Use to drive the iterate-fix loop when adapting decks for mobile."
summary: "Headless Chromium walks every .slide of a Pvragon HTML presentation at a phone-landscape viewport (default 844x390) and measures slide.scrollHeight - slide.clientHeight per slide. Reports overflow + identifies custom component classes per slide so CSS targeting decisions are deterministic. Pairs with the html-presentation manual pathway documented in markdown-to-branded-doc/SKILL.md."
version: 1.0.0
created: 2026-04-30
last_updated: 2026-04-30
maintainer: pvragon
dependencies: [node, playwright]
---

# Mobile Overflow Audit

Walks a Pvragon HTML presentation slide by slide at a phone-landscape viewport and reports content overflow per slide. Eliminates the back-and-forth of "user tells me which slide overflows" — answers it directly.

## When to Use

- After applying responsive CSS to a deck, to verify all slides fit
- Before pushing a new mobile-responsive deck to production
- When iterating on the landscape-phone media query rules — re-run after each tighten to see what's left

## How It Works

```
URL → Playwright (Chromium headless, 844x390 viewport)
    → for each .slide:
         force .active class
         measure scrollHeight vs clientHeight
         capture heading + child component classes
    → return JSON report
```

The viewport defaults to 844x390 (iPhone 14 Pro landscape — middle-of-the-road phone landscape). Override via `--viewport` flag for other sizes.

## Usage

```bash
node skills/mobile-overflow-audit/scripts/audit.js <url> [--viewport WxH] [--threshold N]
```

**Options:**
- `<url>` — fully-qualified URL of the deck (e.g. `https://prez.prgn.ai/pvragon/ai-workspace-intro`). Local file paths supported via `file://...` if Playwright permissions allow.
- `--viewport WxH` — override viewport (default `844x390`). Common sizes: `844x390` (iPhone 14 Pro landscape), `915x412` (Galaxy S23 landscape), `568x320` (iPhone SE landscape).
- `--threshold N` — only report slides overflowing by more than N pixels (default `5` to filter rendering noise).
- `--all` — report all slides, including those that fit.

**Output (stdout, JSON):**
```json
{
  "url": "https://prez.prgn.ai/pvragon/ai-workspace-intro",
  "viewport": { "w": 844, "h": 390 },
  "slideCount": 10,
  "worstOverflow": 84,
  "overflowing": [
    {
      "idx": 1,
      "heading": "AI Is Powerful, But Unreliable Alone",
      "scrollH": 402,
      "clientH": 318,
      "overflow": 84,
      "components": ["bullet-list", "stat-callout"]
    }
  ]
}
```

The `components` array lists distinct component classes the script saw inside the slide. Useful for deciding which CSS rules to target (e.g. if a slide has `tier-stack` and is overflowing, you know to add a `.tier-stack` landscape-phone rule).

## Iterate-Fix Workflow

Typical loop, ~3-5 iterations to convergence:

1. **Audit:** `node audit.js https://prez.prgn.ai/pvragon/<deck>` → get current overflow report
2. **Inspect:** identify the worst-overflowing slide and its components
3. **Fix:** add CSS rules to the `@media (max-height: 500px) and (orientation: landscape)` block of the deck targeting those components
4. **Push:** commit + push, wait for Vercel rebuild
5. **Re-audit:** run the script again, confirm the overflow has dropped
6. **Repeat** until `worstOverflow` is below `threshold` (5px is fine — sub-pixel rounding noise)

## Scope Limitations

- **Pvragon-template-only.** Assumes the deck has `.slide` divs that get `.active` added/removed for visibility, the same JS structure used by all Pvragon HTML presentations. Other deck formats need their own audit logic.
- **Single fixed viewport per run.** Doesn't sweep multiple viewports automatically; pass `--viewport` to test different sizes one at a time.
- **Visual issues invisible.** Detects overflow but not visual ugliness (font weight, alignment, etc.). Use Chrome DevTools mobile emulation for visual review.
- **Vercel cache lag.** After pushing, Vercel takes ~30s to rebuild. The script hits the live URL so allow that lag before re-auditing, or pass a cachebust query string.

## Companion Skill

`markdown-to-branded-doc/SKILL.md` documents the Pvragon HTML presentation manual pathway (template path, substitution recipe, slide structure). This audit script verifies a deck built via that pathway is mobile-ready.

## File Structure

```
skills/mobile-overflow-audit/
├── SKILL.md                     ← this file
└── scripts/
    └── audit.js                 ← Node + Playwright audit script
```

## Dependencies

- `node` (>=18)
- `playwright` (`npm install playwright`)
- `@playwright/browser-chromium` (auto-fetched on first run via `npx playwright install chromium`)
