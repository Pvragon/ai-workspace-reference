#!/usr/bin/env node
/**
 * build-brand-theme.mjs — the reusable brand-token → Untitled UI theme bridge.
 *
 * Reads a W3C brand-tokens.json (from team-lib create-brand-guidelines) and emits:
 *   - src/styles/brand.css  : @theme override that reskins the whole Untitled UI set.
 *   - src/brand.config.ts   : per-brand identity (name/tagline/url) for metadata.
 *
 * The per-brand SURFACE is: brand-tokens.json (→ both files above, generated) PLUS
 * the font imports in src/app/layout.tsx (next/font is a static import — the one
 * manual step per brand; the generator emits the matching --font var names).
 *
 * Color: sRGB<->OKLCH (Ottosson) with proper GAMUT MAPPING (chroma compression),
 * so saturated brands don't produce channel-clipped, hue-shifted, muddy stops.
 * Zero runtime deps. Usage: node scripts/build-brand-theme.mjs [tokens.json]
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
// Output paths. Default = this app's layout (src/styles + src/). Set BRAND_OUT_DIR to
// retarget all three into one dir — lets the generator drop into ANY repo layout (e.g.
// seeding a Nextbase kit) without editing constants.
const STYLES_DIR = process.env.BRAND_OUT_DIR ? resolve(process.env.BRAND_OUT_DIR) : resolve(__dirname, "../src/styles");
const CFG_DIR = process.env.BRAND_OUT_DIR ? resolve(process.env.BRAND_OUT_DIR) : resolve(__dirname, "../src");
const OUT_CSS = resolve(STYLES_DIR, "brand.css");
const OUT_CFG = resolve(CFG_DIR, "brand.config.ts");
// Dual-stack: the SAME tokens also emit a shadcn / Base UI theme (:root CSS vars +
// @theme inline). Untitled UI (brand.css) skins marketing/brand surfaces; shadcn
// (brand-shadcn.css) skins Nextbase app surfaces. Both render the identical brand.
// See team-lib skills/build-brand-site/reference/dual-stack-architecture.md.
const OUT_SHADCN = resolve(STYLES_DIR, "brand-shadcn.css");
// Input: prefer the app-VENDORED copy (web/brand-tokens.json) — it's inside the
// Vercel build context (which is web/ only). Fall back to the repo-root SOURCE for
// local dev. Re-copy the source into web/ when the brand changes (see PATTERNS).
const CANDIDATES = [resolve(__dirname, "../brand-tokens.json"), resolve(__dirname, "../../brand/brand-tokens.json")];
const TOKENS = process.argv[2] ? resolve(process.argv[2]) : (CANDIDATES.find(existsSync) ?? CANDIDATES[0]);

// Resilience: if the tokens can't be found but the generated brand.css already
// exists (committed), keep it and no-op rather than failing the build.
if (!existsSync(TOKENS)) {
  if (existsSync(OUT_CSS)) {
    console.warn(`⚠ brand-tokens.json not found (${TOKENS}); keeping committed brand.css.`);
    process.exit(0);
  }
  throw new Error(`brand-tokens.json not found at any of: ${CANDIDATES.join(", ")}`);
}

// ---- color math (Ottosson OKLab/OKLCH) --------------------------------------
const clamp01 = (x) => Math.min(1, Math.max(0, x));
const srgbToLin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const linToSrgb = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

const hexToRgb = (hex) => { const h = hex.replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255); };
function rgbToOklch([r, g, b]) {
  const R = srgbToLin(r), G = srgbToLin(g), B = srgbToLin(b);
  const l = 0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B;
  const m = 0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B;
  const s = 0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B;
  const l_ = Math.cbrt(l), m_ = Math.cbrt(m), s_ = Math.cbrt(s);
  const L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_;
  const a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_;
  const bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_;
  let H = (Math.atan2(bb, a) * 180) / Math.PI; if (H < 0) H += 360;
  return { L, C: Math.hypot(a, bb), H };
}
function oklchToSrgb({ L, C, H }) {
  const hr = (H * Math.PI) / 180, a = C * Math.cos(hr), b = C * Math.sin(hr);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
  return [
    +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ].map(linToSrgb); // gamma-encoded sRGB, may be out of [0,1]
}
const inGamut = (rgb, eps = 0.001) => rgb.every((c) => c >= -eps && c <= 1 + eps);
// Gamut MAP by compressing chroma (keeps L and H — hue-preserving tint), not per-channel clamp.
function fit({ L, C, H }) {
  let c = C;
  if (!inGamut(oklchToSrgb({ L, C, H }))) {
    let lo = 0, hi = C;
    for (let i = 0; i < 24; i++) { const mid = (lo + hi) / 2; inGamut(oklchToSrgb({ L, C: mid, H })) ? (lo = mid) : (hi = mid); }
    c = lo;
  }
  return oklchToSrgb({ L, C: c, H }).map((x) => Math.round(clamp01(x) * 255));
}
const rgb255 = (hex) => hexToRgb(hex).map((c) => Math.round(c * 255));
const rgbStr = (arr) => `rgb(${arr[0]} ${arr[1]} ${arr[2]})`;
function contrastWhite(rgb) { // WCAG ratio of white vs an rgb triple
  const lum = (arr) => { const [r, g, b] = arr.map((v) => srgbToLin(v / 255)); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const l = lum(rgb); return 1.05 / (l + 0.05);
}

// ---- load tokens ------------------------------------------------------------
const tokens = JSON.parse(readFileSync(TOKENS, "utf8"));
const col = (p) => p.split(".").reduce((o, k) => (o ? o[k] : undefined), tokens.color)?.$value;
const primaryHex = col("brand.primary");
if (!primaryHex) throw new Error("brand-tokens.json: color.brand.primary missing");
const warnings = [];

// ---- BRAND ramp: stop 600 = brand primary (guarded so a LIGHT primary still
// gives a usable white-on-solid CTA); lighter/darker relative to primary L. ----
let base = rgbToOklch(hexToRgb(primaryHex));
let solid = rgb255(primaryHex);
if (contrastWhite(solid) < 4.5) {
  // Light/vivid primary: darken the 600 anchor until white text on the solid passes AA.
  let L = base.L;
  while (L > 0.05 && contrastWhite(fit({ L, C: base.C, H: base.H })) < 4.5) L -= 0.01;
  solid = fit({ L, C: base.C, H: base.H });
  base = { ...base, L };
  warnings.push(`primary ${primaryHex} is too light for white-on-solid; darkened brand-600 to ${rgbStr(solid)} for AA CTA`);
}
const LTOP = 0.972;
const LIGHTER = { 50: [1.0, 0.2], 100: [0.91, 0.34], 200: [0.8, 0.54], 300: [0.65, 0.74], 400: [0.48, 0.9], 500: [0.28, 1.0] };
const DARKER = { 700: [0.88, 0.98], 800: [0.75, 0.9], 900: [0.64, 0.76], 950: [0.48, 0.58] };
const BRAND_ORDER = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
const brandStop = (s) => {
  if (s === 600) return solid;
  if (LIGHTER[s]) { const [t, cf] = LIGHTER[s]; return fit({ L: base.L + (LTOP - base.L) * t, C: base.C * cf, H: base.H }); }
  const [f, cf] = DARKER[s]; return fit({ L: base.L * f, C: base.C * cf, H: base.H });
};
const brandLines = BRAND_ORDER.map((s) => `    --color-brand-${s}: ${rgbStr(brandStop(s))};`);

// ---- WARM NEUTRAL ramp: hue/chroma from a MID-tone warm token (Muted), which
// is numerically stable (unlike near-black Ink) and captures brand temperature.
const mutedHex = col("text.subtle") || col("text.default") || "#555";
const nOk = rgbToOklch(hexToRgb(mutedHex));
const nH = nOk.H, nC = Math.min(nOk.C, 0.016);
const NEUTRAL_L = { 50: 0.972, 100: 0.945, 200: 0.898, 300: 0.828, 400: 0.715, 500: 0.612, 600: 0.512, 700: 0.432, 800: 0.36, 900: 0.285, 950: 0.205 };
const neutralLines = Object.entries(NEUTRAL_L).map(([s, L]) => `    --color-neutral-${s}: ${rgbStr(fit({ L, C: nC, H: nH }))};`);

// ---- SEMANTIC overrides ------------------------------------------------------
// KEY FIX (#1): page ground != surface. Surfaces (bg-primary) are RAISED warm
// near-white from the neutral ramp; the page body is painted from Peach separately.
const pageGround = col("background.default"); // Peach — page body only
const semantic = {
  // raised surfaces (cards, inputs, menus, secondary/tertiary button fills)
  "--color-bg-primary": "var(--color-neutral-50)",
  "--color-bg-primary_hover": "var(--color-neutral-100)",
  "--color-bg-secondary": "var(--color-neutral-100)",
  "--color-bg-secondary_hover": "var(--color-neutral-200)",
  "--color-bg-tertiary": "var(--color-neutral-200)",
  "--color-bg-active": "var(--color-neutral-100)",
  // text: distinct 4-level warm ramp (fix #10 — tertiary != secondary)
  "--color-text-primary": rgbStr(rgb255(col("text.default"))),
  "--color-text-secondary": rgbStr(rgb255(col("text.subtle"))),
  "--color-text-secondary_hover": "var(--color-neutral-800)",
  // ALL readable text must clear AA (4.5) on the warm page — neutral-500 fails at
  // 3.2:1, so tertiary/quaternary/placeholder all use neutral-600 (4.84:1). Placeholder
  // is text a user reads (form inputs), so it must pass too.
  "--color-text-tertiary": "var(--color-neutral-600)",
  "--color-text-quaternary": "var(--color-neutral-600)",
  "--color-text-placeholder": "var(--color-neutral-600)",
  // FUNCTIONAL borders must pass WCAG 1.4.11 non-text 3:1 on the warm surface, so
  // they use a warm neutral — NOT the light decorative Brass Rule (1.67:1, invisible).
  "--color-border-primary": "var(--color-neutral-500)",
  "--color-border-secondary": "var(--color-neutral-300)",
  "--color-border-tertiary": "var(--color-neutral-200)",
  // Decorative-only brass rule (dividers/accents where 3:1 isn't required).
  "--color-brand-rule": rgbStr(rgb255(col("border.default"))),
  // fg (icons)
  "--color-fg-primary": rgbStr(rgb255(col("text.default"))),
  "--color-fg-secondary": rgbStr(rgb255(col("text.subtle"))),
  "--color-fg-quaternary": "var(--color-neutral-400)",
  // Error TEXT must pass AA on the warm surface — UUI's default vivid red-600 is
  // only 4.23:1 there. Darken to red-700 (≈6.2:1) for readable form validation.
  "--color-text-error-primary": "var(--color-red-700)",
  "--color-text-error-primary_hover": "var(--color-red-800)",
  "--color-fg-error-primary": "var(--color-red-700)",
};
// Brand STATUS + LINK (fix #5): success -> Jade, link -> Wisteria. (error/warning
// kept as UUI defaults to stay clearly distinct from the red brand; see TODO.)
const jade = col("status.successDark") || col("brand.tertiary");
const jadeTint = col("status.successLight");
if (jade) Object.assign(semantic, {
  "--color-fg-success-primary": rgbStr(rgb255(jade)),
  "--color-text-success-primary": rgbStr(rgb255(jade)),
  "--color-bg-success-solid": rgbStr(rgb255(jade)),
  "--color-featured-icon-light-fg-success": rgbStr(rgb255(jade)),
  ...(jadeTint ? { "--color-bg-success-primary": rgbStr(rgb255(jadeTint)) } : {}),
});
const semanticLines = Object.entries(semantic).filter(([, v]) => v).map(([k, v]) => `    ${k}: ${v};`);

// ---- fonts ------------------------------------------------------------------
const fontPrimary = tokens.typography?.font?.primary?.$value || "system-ui";
const fontSecondary = tokens.typography?.font?.secondary?.$value || "Georgia";
const cssVar = (n) => "--font-" + n.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const bodyVar = cssVar(fontPrimary), displayVar = cssVar(fontSecondary);
const link = col("link.default"); // Wisteria — prose links

// ---- emit brand.css ---------------------------------------------------------
const css = `/* GENERATED by scripts/build-brand-theme.mjs from brand/brand-tokens.json.
   Brand: ${tokens.company?.name || "unknown"} · primary ${primaryHex} (${col("brand.primary") && tokens.color.brand.primary.$description}).
   Do NOT edit by hand — re-run the generator (npm run theme). Per-brand surface:
   this file + src/brand.config.ts (both generated) + font imports in layout.tsx. */
@theme {
    /* Brand ramp — 600 = brand primary (guarded for white-on-solid AA). */
${brandLines.join("\n")}

    /* Warm neutral ramp (hue from ${mutedHex}) — reskins UUI gray semantics. */
${neutralLines.join("\n")}

    /* Semantic overrides: raised surfaces vs page ground, warm text/borders, brand status. */
${semanticLines.join("\n")}

    /* Fonts (CSS vars registered by next/font in layout.tsx). */
    --font-body: var(${bodyVar}), "${fontPrimary}", -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    --font-display: var(${displayVar}), "${fontSecondary}", Georgia, "Times New Roman", serif;
}

@layer base {
    /* Page ground is the brand background, NOT the raised surface token. */
    html, body { background-color: ${rgbStr(rgb255(pageGround))}; color: var(--color-text-primary); }
${link ? `    /* Prose links in the brand link color. */\n    .prose { --tw-prose-links: ${rgbStr(rgb255(link))}; }` : ""}
}
`;

// ---- emit brand.config.ts (identity for metadata — shrinks the per-brand surface) ----
const c = tokens.company || {};
if (!c.website || /vercel\.app/.test(c.website)) warnings.push(`company.website is missing or a preview URL (${c.website || "none"}) — set the canonical domain in brand-tokens.json`);
const cfg = `// GENERATED by scripts/build-brand-theme.mjs — do not edit by hand.
export const brand = {
  name: ${JSON.stringify(c.name || "Brand")},
  tagline: ${JSON.stringify(c.tagline || "")},
  url: ${JSON.stringify(c.website || "https://example.com")},
} as const;
`;

// ---- emit brand-shadcn.css (dual-stack: shadcn / Base UI target) ------------
// Same brand, shadcn's :root token names. Neutral ramp reuses the warm hue/chroma
// computed above (nH, nC) so the two stacks are pixel-identical on shared colors.
const N = (L) => rgbStr(fit({ L, C: nC, H: nH })); // warm neutral at lightness L
const onPrimary = col("text.onPrimary") ? rgbStr(rgb255(col("text.onPrimary"))) : "rgb(255 255 255)";
const inkC = rgbStr(rgb255(col("text.default")));
const mutedC = rgbStr(rgb255(col("text.subtle")));
const groundC = rgbStr(rgb255(pageGround));
const primaryC = rgbStr(solid);
const wisteria = col("brand.accent") || col("link.default");
// destructive: a deep red kept DISTINCT from the (crimson) brand primary; AA on light.
const destructive = "rgb(185 28 28)";
const charts = [primaryC, wisteria ? rgbStr(rgb255(wisteria)) : N(0.5), jade ? rgbStr(rgb255(jade)) : N(0.6),
  col("border.default") ? rgbStr(rgb255(col("border.default"))) : N(0.72), mutedC];
const shadcnPairs = {
  "--background": groundC, "--foreground": inkC,
  "--card": N(0.972), "--card-foreground": inkC,
  "--popover": N(0.972), "--popover-foreground": inkC,
  "--primary": primaryC, "--primary-foreground": onPrimary,
  "--secondary": N(0.945), "--secondary-foreground": inkC,
  "--muted": N(0.945), "--muted-foreground": mutedC,
  "--accent": N(0.945), "--accent-foreground": inkC,
  "--destructive": destructive, "--destructive-foreground": "rgb(255 255 255)",
  // --border decorative (subtle); --input functional (form fields, more visible);
  // --ring = brand (the real focus indicator). Bump --input/--border to N(0.612)
  // if a reviewer requires strict WCAG 3:1 on every functional border.
  "--border": N(0.828), "--input": N(0.715), "--ring": primaryC,
  "--chart-1": charts[0], "--chart-2": charts[1], "--chart-3": charts[2], "--chart-4": charts[3], "--chart-5": charts[4],
};
const shadcnDark = {
  "--background": N(0.205), "--foreground": N(0.972),
  "--card": N(0.285), "--card-foreground": N(0.972),
  "--popover": N(0.285), "--popover-foreground": N(0.972),
  "--primary": primaryC, "--primary-foreground": onPrimary,
  "--secondary": N(0.36), "--secondary-foreground": N(0.972),
  "--muted": N(0.36), "--muted-foreground": N(0.715),
  "--accent": N(0.36), "--accent-foreground": N(0.972),
  "--destructive": "rgb(239 68 68)", "--destructive-foreground": N(0.972),
  "--border": N(0.36), "--input": N(0.432), "--ring": primaryC,
};
const line = (o) => Object.entries(o).map(([k, v]) => `    ${k}: ${v};`).join("\n");
const themeInline = Object.keys(shadcnPairs).filter((k) => k !== "--radius").map((k) =>
  `    --color-${k.slice(2)}: var(${k});`).join("\n");
const shadcnCss = `/* GENERATED by scripts/build-brand-theme.mjs — shadcn / Base UI target.
   Brand: ${tokens.company?.name || "unknown"} · same brand as brand.css (Untitled UI).
   Import into a shadcn/Nextbase app's globals.css. Dark block is UNVALIDATED — audit
   before enabling. Do NOT edit by hand — re-run the generator. */
:root {
    --radius: 0.75rem;
${line(shadcnPairs)}
}

/* UNVALIDATED dark ramp — inverts the warm neutral scale; audit contrast before shipping. */
.dark {
${line(shadcnDark)}
}

@theme inline {
${themeInline}
    --radius-sm: calc(var(--radius) - 4px);
    --radius-md: calc(var(--radius) - 2px);
    --radius-lg: var(--radius);
    --radius-xl: calc(var(--radius) + 4px);
}
`;

mkdirSync(dirname(OUT_CSS), { recursive: true });
writeFileSync(OUT_CSS, css);
writeFileSync(OUT_CFG, cfg);
writeFileSync(OUT_SHADCN, shadcnCss);
// contrast self-check on the shadcn light pairs the eye can't verify
const ratio = (fg, bg) => { const p = (s) => s.match(/\d+/g).map(Number); const L = (a) => { const [r, g, b] = a.map((v) => srgbToLin(v / 255)); return 0.2126 * r + 0.7152 * g + 0.0722 * b; }; const l1 = L(p(fg)), l2 = L(p(bg)); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
const checks = [["primary/on", onPrimary, primaryC, 4.5], ["muted-fg/muted", mutedC, N(0.945), 4.5], ["fg/bg", inkC, groundC, 4.5]];
console.log(`✓ ${OUT_CSS}`);
console.log(`✓ ${OUT_CFG}`);
console.log(`✓ ${OUT_SHADCN} (shadcn/Base UI target)`);
console.log(`  brand-600 ${rgbStr(solid)} · white-on-solid ${contrastWhite(solid).toFixed(2)}:1`);
console.log(`  page ground ${rgbStr(rgb255(pageGround))} · surface = neutral-50 (raised)`);
checks.forEach(([n, fg, bg, min]) => { const r = ratio(fg, bg); console.log(`  shadcn ${n}: ${r.toFixed(2)}:1 ${r >= min ? "✓" : "✗ FAILS AA"}`); if (r < min) warnings.push(`shadcn ${n} contrast ${r.toFixed(2)} < ${min}`); });
warnings.forEach((w) => console.warn(`  ⚠ ${w}`));
