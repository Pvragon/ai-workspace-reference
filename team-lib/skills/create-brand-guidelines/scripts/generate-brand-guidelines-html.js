#!/usr/bin/env node
/**
 * generate-brand-guidelines-html.js
 *
 * Reads brand-tokens.json and produces a designer-quality HTML brand guidelines
 * document. All values are read from tokens — nothing is hardcoded to a specific
 * brand. The HTML is self-contained (inline CSS, Google Fonts via CDN) and
 * print-ready with landscape orientation and page breaks.
 *
 * Usage:
 *   node generate-brand-guidelines-html.js <path-to-brand-tokens.json> <output-dir>
 */

const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function val(tokenObj) {
  if (!tokenObj) return null;
  if (typeof tokenObj === 'string') return tokenObj;
  return tokenObj.$value ?? tokenObj.value ?? null;
}

function desc(tokenObj) {
  if (!tokenObj) return '';
  return tokenObj.$description ?? tokenObj.description ?? '';
}

function contrastLabel(level) {
  if (!level) return { text: '\u2014', cls: 'neutral' };
  const l = level.toLowerCase();
  if (l === 'aaa') return { text: 'AAA', cls: 'pass-aaa' };
  if (l === 'aa') return { text: 'AA', cls: 'pass-aa' };
  if (l.startsWith('aa')) return { text: level, cls: 'pass-aa-large' };
  return { text: 'Fail', cls: 'fail' };
}

function luminance(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return 0;
  const [r, g, b] = [rgb.r, rgb.g, rgb.b].map(c => {
    c = c / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function hexToRgb(hex) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!m) return null;
  return { r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16) };
}

function textColorFor(bgHex) {
  const L = luminance(bgHex);
  return L > 0.35 ? '#303030' : '#FFFFFF';
}

function contrastRatio(hex1, hex2) {
  const L1 = luminance(hex1);
  const L2 = luminance(hex2);
  const lighter = Math.max(L1, L2);
  const darker = Math.min(L1, L2);
  return (lighter + 0.05) / (darker + 0.05);
}

/** Returns accent if it passes AA contrast (>=3:1) on bgHex, else tertiary as fallback */
function safeAccentOnBg(bgHex) {
  const ratio = contrastRatio(accent, bgHex);
  return ratio >= 3 ? accent : tertiary;
}

function toBase64DataUri(filePath) {
  try {
    const buf = fs.readFileSync(filePath);
    const ext = path.extname(filePath).slice(1).toLowerCase();
    const mime = ext === 'svg' ? 'image/svg+xml' : `image/${ext}`;
    return `data:${mime};base64,${buf.toString('base64')}`;
  } catch {
    return null;
  }
}

function camelToTitle(str) {
  return str.replace(/([A-Z])/g, ' $1').replace(/^./, s => s.toUpperCase()).trim();
}

function resolveTokenPath(tokenPath, tokens) {
  // Resolve "color.brand.primary" to the actual hex value
  const parts = tokenPath.split('.');
  let node = tokens;
  for (const p of parts) {
    if (!node || typeof node !== 'object') return null;
    node = node[p];
  }
  return val(node);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const tokensPath = process.argv[2];
const outputDir = process.argv[3];

if (!tokensPath || !outputDir) {
  console.error('Usage: node generate-brand-guidelines-html.js <tokens.json> <output-dir>');
  process.exit(1);
}

const tokens = JSON.parse(fs.readFileSync(tokensPath, 'utf-8'));

// Extract key values
const brandName = tokens.company?.name ?? 'Brand';
const tagline = tokens.company?.tagline ?? '';
const primary = val(tokens.color?.brand?.primary) ?? '#333333';
const accent = val(tokens.color?.brand?.accent) ?? '#0066FF';
const tertiary = val(tokens.color?.brand?.tertiary) ?? '#666666';
const primaryDesc = desc(tokens.color?.brand?.primary);
const accentDesc = desc(tokens.color?.brand?.accent);
const tertiaryDesc = desc(tokens.color?.brand?.tertiary);

const textDefault = val(tokens.color?.text?.default) ?? '#303030';
const textSubtle = val(tokens.color?.text?.subtle) ?? '#808080';
const bgDefault = val(tokens.color?.background?.default) ?? '#FFFFFF';
const bgSubtle = val(tokens.color?.background?.subtle) ?? '#F0F0F0';
const bgAccent = val(tokens.color?.background?.accent) ?? '#E8F4F4';
const borderDefault = val(tokens.color?.border?.default) ?? '#DAD9D9';
const borderSubtle = val(tokens.color?.border?.subtle) ?? '#ECECEC';

const fontPrimary = val(tokens.typography?.font?.primary) ?? 'Inter';
const fontSecondary = val(tokens.typography?.font?.secondary) ?? 'Inter';
const fontMono = val(tokens.typography?.font?.monospace) ?? 'Courier New';

const gradientLight = val(tokens.color?.extended?.gradientLight) ?? primary;
const gradientDark = val(tokens.color?.extended?.gradientDark) ?? tertiary;

// Logo embedding
const logoWhite = tokens.logo?.fullOnDark?.absolutePath
  ? toBase64DataUri(tokens.logo.fullOnDark.absolutePath) : null;
const logoColor = tokens.logo?.full?.absolutePath
  ? toBase64DataUri(tokens.logo.full.absolutePath) : null;
const iconColor = tokens.logo?.icon?.absolutePath
  ? toBase64DataUri(tokens.logo.icon.absolutePath) : null;

// Google Fonts URL
const fontsToLoad = [...new Set([fontPrimary, fontSecondary].filter(Boolean))];
const googleFontsUrl = `https://fonts.googleapis.com/css2?${fontsToLoad
  .map(f => `family=${encodeURIComponent(f)}:wght@300;400;500;600;700;800`)
  .join('&')}&display=swap`;

// Schema version
const schemaVersion = (tokens.$schema ?? 'v1').replace('brand-tokens-', '');

// ---------------------------------------------------------------------------
// Build color swatch collections
// ---------------------------------------------------------------------------

function buildSwatchGrid(colorGroup, prefix) {
  if (!colorGroup) return [];
  return Object.entries(colorGroup).map(([key, tok]) => ({
    name: `${prefix}.${key}`,
    label: desc(tok) || camelToTitle(key),
    value: val(tok),
  })).filter(s => s.value);
}

const extendedSwatches = buildSwatchGrid(tokens.color?.extended, 'extended');
const textSwatches = buildSwatchGrid(tokens.color?.text, 'text');
const bgSwatches = buildSwatchGrid(tokens.color?.background, 'background');
const borderSwatches = buildSwatchGrid(tokens.color?.border, 'border');
const linkSwatches = buildSwatchGrid(tokens.color?.link, 'link');
const statusSwatches = buildSwatchGrid(tokens.color?.status, 'status');

// Derivative tint/shade families
function buildDerivativeFamily(familyTokens) {
  if (!familyTokens) return [];
  return Object.entries(familyTokens).map(([key, tok]) => ({
    name: key,
    label: desc(tok) || key,
    value: val(tok),
  })).filter(s => s.value);
}

const derivPrimary = buildDerivativeFamily(tokens.color?.derivative?.primary);
const derivAccent = buildDerivativeFamily(tokens.color?.derivative?.accent);
const derivTertiary = buildDerivativeFamily(tokens.color?.derivative?.tertiary);

// Weights
const weights = tokens.typography?.weight
  ? Object.entries(tokens.typography.weight).map(([k, v]) => ({ name: k, value: val(v) }))
  : [];

// Accessibility
const accessResults = tokens.accessibility?.computed ?? [];

// Voice
const voice = tokens.voice ?? {};

// Company
const company = tokens.company ?? {};

// Preferences
const preference = tokens.preference ?? {};

// Coverage
const coverage = tokens.$generated?.coverage ?? {};

// ---------------------------------------------------------------------------
// Page footer helper
// ---------------------------------------------------------------------------
function pageFooter(pageNum) {
  return `<div class="page-footer">
    <div class="page-footer-brand">
      ${iconColor ? `<img src="${iconColor}" alt="">` : ''}
      <span>${brandName} Brand Guidelines</span>
    </div>
    <span>${pageNum}</span>
  </div>`;
}

// ---------------------------------------------------------------------------
// Mini swatch helper
// ---------------------------------------------------------------------------
function miniSwatch(color, label, tokenName) {
  const fg = textColorFor(color);
  return `<div class="mini-swatch">
      <div class="mini-color" style="background:${color}; color:${fg};">
        <span class="mini-hex">${color}</span>
      </div>
      <div class="mini-meta">
        <span class="mini-label">${label}</span>
        <span class="mini-token">${tokenName}</span>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Derivative row helper
// ---------------------------------------------------------------------------
function derivativeRow(familyName, familyColor, swatches) {
  if (!swatches.length) return '';
  return `<div class="deriv-family">
      <div class="deriv-header">
        <div class="deriv-dot" style="background:${familyColor};"></div>
        <span class="deriv-name-label">${familyName}</span>
      </div>
      <div class="deriv-chips">
        ${swatches.map(s => {
          const fg = textColorFor(s.value);
          return `<div class="deriv-chip" style="background:${s.value}; color:${fg};">
            <span class="dc-name">${s.name}</span>
            <span class="dc-hex">${s.value}</span>
          </div>`;
        }).join('')}
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// HTML
// ---------------------------------------------------------------------------

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${brandName} \u2014 Brand Guidelines</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="${googleFontsUrl}" rel="stylesheet">
<style>
/* ===== RESET ===== */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
html{font-size:16px;-webkit-print-color-adjust:exact;print-color-adjust:exact;}
body{
  font-family:'${fontPrimary}','${fontSecondary}',Arial,sans-serif;
  color:${textDefault};
  background:#2a2a2a;
  line-height:1.5;
}

/* ===== PRINT ===== */
@page{size:11in 8.5in landscape;margin:0;}
@media print{body{background:#fff;}.page{box-shadow:none!important;margin:0!important;}}

/* ===== PAGE SHELL ===== */
.page{
  width:11in;height:8.5in;
  position:relative;overflow:hidden;
  page-break-after:always;page-break-inside:avoid;
  margin:24px auto;
  box-shadow:0 4px 40px rgba(0,0,0,0.45);
  background:${bgDefault};
}

/* ===== COVER ===== */
.page-cover{
  background:linear-gradient(135deg, ${gradientLight} 0%, ${gradientDark} 60%, ${tertiary} 100%);
  display:flex;flex-direction:column;
  justify-content:center;align-items:flex-start;
  padding:0 1.4in;color:#FFFFFF;
}
.cover-accent-stripe{
  position:absolute;top:0;right:280px;bottom:0;width:4px;
  background:${accent};opacity:0.35;
}
.cover-geo{
  position:absolute;bottom:-80px;right:-80px;
  width:420px;height:420px;
  border-radius:50%;
  border:60px solid ${accent};
  opacity:0.06;
}
.cover-geo-2{
  position:absolute;top:-120px;right:160px;
  width:260px;height:260px;
  border-radius:50%;
  background:rgba(255,255,255,0.04);
}
.cover-logo{height:52px;margin-bottom:56px;}
.cover-bar{width:64px;height:4px;background:${accent};border-radius:2px;margin-bottom:28px;}
.cover-title{
  font-family:'${fontSecondary}',sans-serif;
  font-size:56px;font-weight:800;letter-spacing:-1.5px;line-height:1.05;margin-bottom:20px;
}
.cover-subtitle{
  font-size:17px;font-weight:300;opacity:0.75;max-width:520px;line-height:1.7;margin-bottom:56px;
}
.cover-meta{
  font-size:11px;font-weight:500;letter-spacing:3px;text-transform:uppercase;opacity:0.4;
}

/* ===== SECTION PAGE ===== */
.page-section{
  display:flex;flex-direction:column;
  padding:52px 64px 36px;
}
.section-header{
  display:flex;align-items:center;gap:14px;margin-bottom:36px;
}
.section-num{
  font-family:'${fontSecondary}',sans-serif;
  font-size:12px;font-weight:700;color:${primary};
  background:${bgAccent};padding:5px 16px;border-radius:20px;letter-spacing:1.5px;
}
.section-title{
  font-family:'${fontSecondary}',sans-serif;
  font-size:26px;font-weight:700;color:${primary};letter-spacing:-0.3px;
}
.section-rule{flex:1;height:1px;background:linear-gradient(90deg,${borderDefault},transparent);}
.section-body{flex:1;display:flex;flex-direction:column;padding-bottom:24px;}

/* Page footer */
.page-footer{
  display:flex;justify-content:space-between;align-items:center;
  padding-top:12px;margin-top:auto;
  border-top:1px solid ${borderSubtle};
  font-size:9px;color:${textSubtle};letter-spacing:0.5px;
}
.page-footer-brand{display:flex;align-items:center;gap:6px;}
.page-footer-brand img{height:12px;opacity:0.5;}

/* ===== DARK PAGE VARIANT ===== */
.page-dark{
  background:linear-gradient(160deg, ${gradientDark} 0%, ${primary} 100%);
  color:#FFFFFF;
}
.page-dark .section-num{
  background:rgba(255,255,255,0.1);color:#FFFFFF;
}
.page-dark .section-title{color:#FFFFFF;}
.page-dark .section-rule{background:linear-gradient(90deg,rgba(255,255,255,0.15),transparent);}
.page-dark .page-footer{border-top-color:rgba(255,255,255,0.1);color:rgba(255,255,255,0.4);}
.page-dark .page-footer-brand img{filter:brightness(10);opacity:0.3;}

/* ===== PALETTE PAGE ACCENT ===== */
.page-palette::before{
  content:'';position:absolute;top:0;right:0;width:200px;height:200px;
  background:${accent};opacity:0.03;border-radius:0 0 0 100%;
}
.page-palette::after{
  content:'';position:absolute;bottom:40px;left:0;width:120px;height:3px;
  background:linear-gradient(90deg,${accent},transparent);margin-left:64px;opacity:0.3;
}

/* ===== HERO PALETTE ===== */
.hero-palette{display:grid;grid-template-columns:1fr 1fr 1fr;gap:28px;flex:1;}
.hero-swatch{
  border-radius:20px;display:flex;flex-direction:column;
  justify-content:flex-end;padding:32px 36px;
  position:relative;overflow:hidden;
  box-shadow:0 12px 40px rgba(0,0,0,0.18),0 2px 8px rgba(0,0,0,0.08);
}
.hero-ring{
  position:absolute;top:24px;right:28px;width:56px;height:56px;
  border-radius:50%;border:2.5px solid currentColor;opacity:0.25;
}
.hero-inner-label{
  font-size:10px;font-weight:600;letter-spacing:2.5px;text-transform:uppercase;
  opacity:0.55;margin-bottom:10px;
}
.hero-name{
  font-family:'${fontSecondary}',sans-serif;
  font-size:24px;font-weight:700;margin-bottom:6px;
}
.hero-hex{
  font-family:'${fontMono}',monospace;font-size:14px;opacity:0.7;letter-spacing:0.5px;
}

/* ===== EXTENDED COLORS ===== */
/*
 * Rule: balanced use of page space — swatches and text should fill the page
 * generously, not cluster at the top. But ALWAYS verify visually that content
 * fits within the page boundary with footer visible. No overflow allowed.
 */
.ext-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px 44px;flex:1;align-content:start;}
.ext-group-title{
  font-family:'${fontSecondary}',sans-serif;
  font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:2px;
  color:${textSubtle};margin-bottom:10px;padding-bottom:5px;
  border-bottom:2px solid ${accent};display:inline-block;
}
.ext-swatches{display:flex;flex-direction:column;gap:5px;}
.mini-swatch{
  display:flex;align-items:center;gap:12px;
  border:1px solid ${borderSubtle};border-radius:12px;padding:4px 14px 4px 4px;
}
.mini-color{
  width:52px;height:52px;border-radius:9px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  box-shadow:inset 0 0 0 1px rgba(0,0,0,0.06);
}
.mini-hex{font-family:'${fontMono}',monospace;font-size:11px;font-weight:600;opacity:0.9;}
.mini-meta{display:flex;flex-direction:column;gap:1px;}
.mini-label{font-size:13px;font-weight:600;color:${textDefault};}
.mini-token{font-family:'${fontMono}',monospace;font-size:10px;color:${textSubtle};}

/* ===== TINTS & SHADES ===== */
.deriv-container{display:flex;flex-direction:column;gap:32px;flex:1;justify-content:center;}
.deriv-family{display:flex;flex-direction:column;gap:12px;}
.deriv-header{display:flex;align-items:center;gap:10px;}
.deriv-dot{width:14px;height:14px;border-radius:50%;box-shadow:0 2px 8px rgba(0,0,0,0.2);}
.deriv-name-label{
  font-family:'${fontSecondary}',sans-serif;
  font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:rgba(255,255,255,0.6);
}
.deriv-chips{display:flex;gap:12px;}
.deriv-chip{
  flex:1;height:88px;border-radius:14px;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
  box-shadow:0 6px 24px rgba(0,0,0,0.15);
}
.dc-name{font-size:9px;font-weight:600;opacity:0.6;text-transform:uppercase;letter-spacing:1.5px;}
.dc-hex{font-family:'${fontMono}',monospace;font-size:12px;font-weight:600;}

/* ===== TYPOGRAPHY ===== */
.type-layout{display:grid;grid-template-columns:1fr 1fr;gap:48px;flex:1;}
.type-specimen{display:flex;flex-direction:column;justify-content:center;}
.type-label{
  font-family:'${fontSecondary}',sans-serif;
  font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2.5px;
  color:${primary};margin-bottom:12px;padding-bottom:6px;
  border-bottom:2px solid ${accent};
  display:inline-block;
}
.type-big{
  font-size:52px;font-weight:800;color:${primary};line-height:1.05;margin-bottom:6px;
}
.type-sample{font-size:15px;font-weight:300;color:${textSubtle};margin-bottom:28px;}
.type-weights{display:flex;flex-direction:column;gap:8px;}
.type-w-row{display:grid;grid-template-columns:80px 36px 1fr;align-items:center;gap:10px;}
.type-w-name{
  font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;
  color:${textSubtle};text-align:left;
}
.type-w-val{font-family:'${fontMono}',monospace;font-size:9px;color:${textSubtle};text-align:left;}
.type-w-bar{height:8px;border-radius:4px;background:linear-gradient(90deg,${primary},${safeAccentOnBg(bgDefault)});}
.type-hierarchy{
  display:flex;flex-direction:column;justify-content:center;gap:8px;
  padding:36px 40px;background:${bgSubtle};border-radius:20px;
  border:1px solid ${borderSubtle};
}
.type-h-item{
  display:flex;align-items:baseline;gap:16px;padding:8px 0;
  border-bottom:1px solid ${borderSubtle};
}
.type-h-item:last-child{border-bottom:none;}
.type-h-tag{
  font-family:'${fontMono}',monospace;font-size:9px;color:${textSubtle};
  width:28px;flex-shrink:0;text-align:right;
}

/* ===== VOICE ===== */
.voice-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;flex:1;}
.voice-card{
  background:${bgDefault};border:1px solid ${borderSubtle};border-radius:20px;
  padding:32px 36px;display:flex;flex-direction:column;position:relative;overflow:hidden;
}
.voice-card::before{
  content:'';position:absolute;top:0;left:0;right:0;height:5px;
  background:linear-gradient(90deg,${primary},${accent});
}
.voice-card-label{
  font-family:'${fontSecondary}',sans-serif;
  font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:2.5px;
  color:${primary};margin-bottom:14px;
}
.voice-card-text{font-size:15px;line-height:1.75;color:${textDefault};}
.voice-card::after{
  content:'\\201C';position:absolute;bottom:8px;right:24px;
  font-family:'${fontSecondary}',serif;font-size:120px;font-weight:800;
  color:${primary};opacity:0.04;line-height:1;
}

/* ===== COMPANY & PREFS ===== */
.info-layout{display:grid;grid-template-columns:1fr 1.5fr;gap:40px;flex:1;}
.info-card{
  background:${bgSubtle};border-radius:20px;padding:32px 36px;
  display:flex;flex-direction:column;gap:12px;
  position:relative;overflow:hidden;
}
.info-card::after{
  content:'';position:absolute;bottom:0;right:0;width:140px;height:140px;
  background:${primary};opacity:0.025;border-radius:100% 0 0 0;
}
.info-card-title{
  font-family:'${fontSecondary}',sans-serif;
  font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:2px;
  color:${primary};padding-bottom:10px;border-bottom:2px solid ${accent};margin-bottom:4px;
}
.info-row{display:flex;justify-content:space-between;align-items:baseline;padding:3px 0;}
.info-row-label{
  font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:${textSubtle};
}
.info-row-value{font-size:14px;font-weight:500;color:${textDefault};text-align:right;max-width:58%;}
.prefs-section{display:flex;flex-direction:column;gap:12px;}
.prefs-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
.pref-group{
  background:${bgDefault};border:1px solid ${borderSubtle};border-radius:14px;padding:16px 18px;
}
.pref-group-title{
  font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;
  color:${primary};margin-bottom:8px;
}
.pref-item{display:flex;justify-content:space-between;font-size:11px;padding:2.5px 0;border-bottom:1px solid ${borderSubtle};}
.pref-item:last-child{border-bottom:none;}
.pref-item-key{color:${textSubtle};font-weight:500;}
.pref-item-val{color:${textDefault};font-weight:600;font-family:'${fontMono}',monospace;}

/* ===== ACCESSIBILITY ===== */
.access-layout{display:grid;grid-template-columns:1.2fr 1fr;gap:36px;flex:1;}
.contrast-table{width:100%;border-collapse:separate;border-spacing:0 5px;}
.contrast-table th{
  font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1px;
  color:${textSubtle};text-align:left;padding:0 10px 6px;
}
.contrast-table td{padding:8px 10px;font-size:13px;background:${bgSubtle};border:none;}
.contrast-table tr td:first-child{border-radius:8px 0 0 8px;}
.contrast-table tr td:last-child{border-radius:0 8px 8px 0;}
.contrast-pair{display:flex;align-items:center;gap:3px;}
.contrast-arrow{color:${textSubtle};font-size:8px;opacity:0.4;}
.contrast-dot{
  width:16px;height:16px;border-radius:4px;
  border:1px solid rgba(0,0,0,0.08);flex-shrink:0;
}
.contrast-token{font-family:'${fontMono}',monospace;font-size:10px;color:${textSubtle};}
.contrast-ratio{font-family:'${fontMono}',monospace;font-weight:700;font-size:14px;}
.badge{
  display:inline-block;padding:2px 10px;border-radius:10px;
  font-size:11px;font-weight:700;letter-spacing:0.5px;
}
.badge.pass-aaa{background:#E6F4EA;color:#1E7E34;}
.badge.pass-aa{background:#E6F4EA;color:#34A853;}
.badge.pass-aa-large{background:#FFF3E0;color:#E65100;}
.badge.fail{background:#FDECEA;color:#C62828;}
.badge.neutral{background:${bgSubtle};color:${textSubtle};}

.coverage-card{
  background:linear-gradient(150deg,${primary} 0%,${gradientDark} 100%);
  border-radius:20px;padding:36px;color:#FFFFFF;
  display:flex;flex-direction:column;justify-content:center;gap:20px;
}
.cov-title{
  font-family:'${fontSecondary}',sans-serif;
  font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:2.5px;opacity:0.5;
}
.cov-big{font-family:'${fontSecondary}',sans-serif;font-size:72px;font-weight:800;line-height:1;}
.cov-stats{display:flex;flex-direction:column;gap:0;}
.cov-row{
  display:flex;justify-content:space-between;font-size:13px;padding:5px 0;
  border-bottom:1px solid rgba(255,255,255,0.1);opacity:0.7;
}
.cov-row:last-child{border-bottom:none;}
.cov-row-val{font-weight:700;opacity:1;}
.target-badges{display:flex;gap:8px;margin-top:6px;}
.target-badge{
  padding:5px 14px;border-radius:8px;background:rgba(255,255,255,0.12);
  font-size:10px;font-weight:600;letter-spacing:0.5px;
}

/* ===== TOKEN REFERENCE ===== */
.token-ref{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;flex:1;overflow:hidden;}
.token-col{display:flex;flex-direction:column;gap:3px;overflow:hidden;}
.tok-group{
  font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;
  color:${primary};margin:16px 0 4px;
}
.tok-group:first-child{margin-top:0;}
.tok-row{
  display:flex;justify-content:space-between;align-items:center;
  font-family:'${fontMono}',monospace;font-size:10.5px;
  padding:2.5px 8px;border-radius:4px;
}
.tok-row:nth-child(odd){background:${bgSubtle};}
.tok-key{color:${textSubtle};}
.tok-val{color:${textDefault};font-weight:600;}
.tok-swatch{
  width:14px;height:14px;border-radius:2px;display:inline-block;
  border:1px solid rgba(0,0,0,0.06);margin-right:5px;vertical-align:middle;
}
.page-dark .tok-group{color:${accent};}
.page-dark .tok-row:nth-child(odd){background:rgba(255,255,255,0.05);}
.page-dark .tok-key{color:rgba(255,255,255,0.5);}
.page-dark .tok-val{color:rgba(255,255,255,0.9);}
</style>
</head>
<body>

<!-- ═══════════════════ PAGE 1: COVER ═══════════════════ -->
<div class="page page-cover">
  <div class="cover-accent-stripe"></div>
  <div class="cover-geo"></div>
  <div class="cover-geo-2"></div>
  ${logoWhite ? `<img class="cover-logo" src="${logoWhite}" alt="${brandName}">` : ''}
  <div class="cover-bar"></div>
  <div class="cover-title">Brand<br>Guidelines</div>
  <div class="cover-subtitle">${tagline}</div>
  <div class="cover-meta">${brandName} Design System &middot; ${schemaVersion}</div>
</div>

<!-- ═══════════════════ PAGE 2: CORE PALETTE ═══════════════════ -->
<div class="page page-section page-palette">
  <div class="section-header">
    <span class="section-num">01</span>
    <span class="section-title">Core Palette</span>
    <div class="section-rule"></div>
  </div>
  <div class="section-body">
    <div class="hero-palette">
      <div class="hero-swatch" style="background:${primary};color:${textColorFor(primary)};">
        <div class="hero-ring"></div>
        <div class="hero-inner-label">Primary</div>
        <div class="hero-name">${primaryDesc || 'Primary'}</div>
        <div class="hero-hex">${primary}</div>
      </div>
      <div class="hero-swatch" style="background:${accent};color:${textColorFor(accent)};">
        <div class="hero-ring"></div>
        <div class="hero-inner-label">Accent</div>
        <div class="hero-name">${accentDesc || 'Accent'}</div>
        <div class="hero-hex">${accent}</div>
      </div>
      <div class="hero-swatch" style="background:${tertiary};color:${textColorFor(tertiary)};">
        <div class="hero-ring"></div>
        <div class="hero-inner-label">Tertiary</div>
        <div class="hero-name">${tertiaryDesc || 'Tertiary'}</div>
        <div class="hero-hex">${tertiary}</div>
      </div>
    </div>
  </div>
  ${pageFooter(2)}
</div>

<!-- ═══════════════════ PAGE 3: EXTENDED COLORS (1/2) ═══════════════════ -->
<div class="page page-section">
  <div class="section-header">
    <span class="section-num">02</span>
    <span class="section-title">Extended Colors</span>
    <div class="section-rule"></div>
  </div>
  <div class="section-body">
    <div class="ext-grid">
      ${[
        { title: 'Text', items: textSwatches },
        { title: 'Background', items: bgSwatches },
        { title: 'Border', items: borderSwatches },
        { title: 'Link', items: linkSwatches },
      ].filter(g => g.items.length).map(g => `
        <div>
          <div class="ext-group-title">${g.title}</div>
          <div class="ext-swatches">
            ${g.items.map(s => miniSwatch(s.value, s.label, s.name)).join('')}
          </div>
        </div>
      `).join('')}
    </div>
  </div>
  ${pageFooter(3)}
</div>

<!-- ═══════════════════ PAGE 4: EXTENDED COLORS (2/2) ═══════════════════ -->
<div class="page page-section">
  <div class="section-header">
    <span class="section-num">02</span>
    <span class="section-title">Extended &amp; Status Colors</span>
    <div class="section-rule"></div>
  </div>
  <div class="section-body">
    <div class="ext-grid">
      ${[
        { title: 'Extended', items: extendedSwatches },
        { title: 'Status', items: statusSwatches },
      ].filter(g => g.items.length).map(g => `
        <div>
          <div class="ext-group-title">${g.title}</div>
          <div class="ext-swatches">
            ${g.items.map(s => miniSwatch(s.value, s.label, s.name)).join('')}
          </div>
        </div>
      `).join('')}
    </div>
  </div>
  ${pageFooter(4)}
</div>

<!-- ═══════════════════ PAGE 5: TINTS & SHADES (DARK) ═══════════════════ -->
<div class="page page-section page-dark">
  <div class="section-header">
    <span class="section-num">03</span>
    <span class="section-title">Tints &amp; Shades</span>
    <div class="section-rule"></div>
  </div>
  <div class="section-body">
    <div class="deriv-container">
      ${derivativeRow('Primary', primary, derivPrimary)}
      ${derivativeRow('Accent', accent, derivAccent)}
      ${derivativeRow('Tertiary', tertiary, derivTertiary)}
    </div>
  </div>
  ${pageFooter(5)}
</div>

<!-- ═══════════════════ PAGE 6: TYPOGRAPHY ═══════════════════ -->
<div class="page page-section">
  <div class="section-header">
    <span class="section-num">04</span>
    <span class="section-title">Typography</span>
    <div class="section-rule"></div>
  </div>
  <div class="section-body">
    <div class="type-layout">
      <div class="type-specimen">
        <div class="type-label">Primary Typeface</div>
        <div class="type-big" style="font-family:'${fontPrimary}',sans-serif;">${fontPrimary}</div>
        <div class="type-sample" style="font-family:'${fontPrimary}',sans-serif;">Aa Bb Cc Dd Ee Ff Gg Hh Ii Jj Kk Ll Mm</div>
        ${fontSecondary !== fontPrimary ? `
        <div class="type-label">Secondary Typeface</div>
        <div class="type-big" style="font-family:'${fontSecondary}',sans-serif;font-size:42px;">${fontSecondary}</div>
        <div class="type-sample" style="font-family:'${fontSecondary}',sans-serif;">Aa Bb Cc Dd Ee Ff Gg Hh Ii Jj Kk Ll Mm</div>
        ` : ''}
        <div class="type-label" style="margin-top:20px;">Weight Scale</div>
        <div class="type-weights">
          ${weights.map(w => `
            <div class="type-w-row">
              <span class="type-w-name">${w.name}</span>
              <span class="type-w-val">${w.value}</span>
              <div class="type-w-bar" style="width:${Math.max(Math.round(w.value / 8), 10)}%;"></div>
            </div>
          `).join('')}
        </div>
      </div>
      <div class="type-hierarchy">
        ${[
          { tag: 'H1', size: 30, weight: 700, color: val(tokens.color?.heading?.h1) ?? primary, font: fontSecondary },
          { tag: 'H2', size: 24, weight: 700, color: val(tokens.color?.heading?.h2) ?? tertiary, font: fontSecondary },
          { tag: 'H3', size: 19, weight: 700, color: val(tokens.color?.heading?.h3) ?? primary, font: fontSecondary },
          { tag: 'H4', size: 16, weight: 700, color: val(tokens.color?.heading?.h4) ?? textDefault, font: fontSecondary },
          { tag: 'H5', size: 13, weight: 700, color: val(tokens.color?.heading?.h5) ?? textDefault, font: fontSecondary },
          { tag: 'H6', size: 12, weight: 700, color: val(tokens.color?.heading?.h6) ?? textDefault, font: fontSecondary },
          { tag: 'P', size: 13, weight: 400, color: textDefault, font: fontPrimary },
        ].map(h => `
          <div class="type-h-item">
            <span class="type-h-tag">${h.tag}</span>
            <span style="font-family:'${h.font}',sans-serif;font-size:${h.size}px;font-weight:${h.weight};color:${h.color};line-height:1.3;">
              The quick brown fox jumps
            </span>
          </div>
        `).join('')}
      </div>
    </div>
  </div>
  ${pageFooter(6)}
</div>

<!-- ═══════════════════ PAGE 7: VOICE & TONE ═══════════════════ -->
<div class="page page-section">
  <div class="section-header">
    <span class="section-num">05</span>
    <span class="section-title">Voice &amp; Tone</span>
    <div class="section-rule"></div>
  </div>
  <div class="section-body">
    <div class="voice-grid">
      ${Object.entries(voice).filter(([, v]) => v).map(([key, value]) => `
        <div class="voice-card">
          <div class="voice-card-label">${camelToTitle(key)}</div>
          <div class="voice-card-text">${value}</div>
        </div>
      `).join('')}
    </div>
  </div>
  ${pageFooter(7)}
</div>

<!-- ═══════════════════ PAGE 8: COMPANY & PREFERENCES ═══════════════════ -->
<div class="page page-section">
  <div class="section-header">
    <span class="section-num">06</span>
    <span class="section-title">Company &amp; Preferences</span>
    <div class="section-rule"></div>
  </div>
  <div class="section-body">
    <div class="info-layout">
      <div class="info-card">
        <div class="info-card-title">Company Information</div>
        ${Object.entries(company).filter(([, v]) => v).map(([key, value]) => `
          <div class="info-row">
            <span class="info-row-label">${camelToTitle(key)}</span>
            <span class="info-row-value">${value}</span>
          </div>
        `).join('')}
      </div>
      <div class="prefs-section">
        <div class="info-card-title">Content Preferences</div>
        <div class="prefs-grid">
          ${Object.entries(preference).filter(([, group]) => {
            if (!group || typeof group !== 'object') return false;
            return Object.values(group).some(v => v !== null);
          }).map(([groupName, group]) => `
            <div class="pref-group">
              <div class="pref-group-title">${camelToTitle(groupName)}</div>
              ${Object.entries(group).filter(([, v]) => v !== null).map(([k, v]) => `
                <div class="pref-item">
                  <span class="pref-item-key">${camelToTitle(k)}</span>
                  <span class="pref-item-val">${v}</span>
                </div>
              `).join('')}
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  </div>
  ${pageFooter(8)}
</div>

<!-- ═══════════════════ PAGE 9: ACCESSIBILITY & COVERAGE ═══════════════════ -->
<div class="page page-section">
  <div class="section-header">
    <span class="section-num">07</span>
    <span class="section-title">Accessibility &amp; Coverage</span>
    <div class="section-rule"></div>
  </div>
  <div class="section-body">
    <div class="access-layout">
      <div>
        <table class="contrast-table">
          <thead>
            <tr><th>Pair</th><th>Foreground</th><th>Background</th><th>Ratio</th><th>Level</th></tr>
          </thead>
          <tbody>
            ${accessResults.map(r => {
              const cl = contrastLabel(r.level);
              const fgColor = resolveTokenPath(r.foreground, tokens) ?? primary;
              const bgColor = resolveTokenPath(r.background, tokens) ?? bgDefault;
              return `<tr>
                <td><div class="contrast-pair">
                  <div class="contrast-dot" style="background:${fgColor};"></div>
                  <span class="contrast-arrow">/</span>
                  <div class="contrast-dot" style="background:${bgColor};"></div>
                </div></td>
                <td><span class="contrast-token">${r.foreground}</span></td>
                <td><span class="contrast-token">${r.background}</span></td>
                <td><span class="contrast-ratio">${r.ratio}:1</span></td>
                <td><span class="badge ${cl.cls}">${cl.text}</span></td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>
      <div class="coverage-card">
        <div class="cov-title">Token Coverage</div>
        <div class="cov-big">${coverage.percent ?? '\u2014'}%</div>
        <div class="cov-stats">
          <div class="cov-row"><span>Total tokens</span><span class="cov-row-val">${coverage.total ?? '\u2014'}</span></div>
          <div class="cov-row"><span>Defined</span><span class="cov-row-val">${coverage.defined ?? '\u2014'}</span></div>
          <div class="cov-row"><span>Derived</span><span class="cov-row-val">${coverage.derived ?? '\u2014'}</span></div>
          <div class="cov-row"><span>Missing</span><span class="cov-row-val">${coverage.missing ?? '\u2014'}</span></div>
        </div>
        <div class="target-badges">
          <div class="target-badge">Text ${tokens.accessibility?.textContrast ?? '\u2014'}</div>
          <div class="target-badge">UI ${tokens.accessibility?.uiContrast ?? '\u2014'}</div>
        </div>
      </div>
    </div>
  </div>
  ${pageFooter(9)}
</div>

<!-- ═══════════════════ PAGE 10: TOKEN REFERENCE (DARK) ═══════════════════ -->
<div class="page page-section page-dark">
  <div class="section-header">
    <span class="section-num">08</span>
    <span class="section-title">Token Reference</span>
    <div class="section-rule"></div>
  </div>
  <div class="section-body">
    <div class="token-ref">
      <div class="token-col">
        <div class="tok-group">Brand Colors</div>
        ${Object.entries(tokens.color?.brand ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key"><span class="tok-swatch" style="background:${val(v)};"></span>color.brand.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
        <div class="tok-group">Text Colors</div>
        ${Object.entries(tokens.color?.text ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key"><span class="tok-swatch" style="background:${val(v)};"></span>color.text.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
        <div class="tok-group">Background</div>
        ${Object.entries(tokens.color?.background ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key"><span class="tok-swatch" style="background:${val(v)};"></span>color.bg.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
        <div class="tok-group">Border</div>
        ${Object.entries(tokens.color?.border ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key"><span class="tok-swatch" style="background:${val(v)};"></span>color.border.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
      </div>
      <div class="token-col">
        <div class="tok-group">Heading Colors</div>
        ${Object.entries(tokens.color?.heading ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key"><span class="tok-swatch" style="background:${val(v)};"></span>color.heading.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
        <div class="tok-group">Link Colors</div>
        ${Object.entries(tokens.color?.link ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key"><span class="tok-swatch" style="background:${val(v)};"></span>color.link.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
        <div class="tok-group">Status Colors</div>
        ${Object.entries(tokens.color?.status ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key"><span class="tok-swatch" style="background:${val(v)};"></span>color.status.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
      </div>
      <div class="token-col">
        <div class="tok-group">Extended Colors</div>
        ${Object.entries(tokens.color?.extended ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key"><span class="tok-swatch" style="background:${val(v)};"></span>color.ext.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
        <div class="tok-group">Typography</div>
        ${Object.entries(tokens.typography?.font ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key">font.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
        ${Object.entries(tokens.typography?.weight ?? {}).map(([k, v]) => `
          <div class="tok-row"><span class="tok-key">weight.${k}</span><span class="tok-val">${val(v)}</span></div>
        `).join('')}
      </div>
    </div>
  </div>
  ${pageFooter(10)}
</div>

</body>
</html>`;

// ---------------------------------------------------------------------------
// Write
// ---------------------------------------------------------------------------

// Use the brand directory name (e.g. "northwind") not company.name (e.g. "Echo One") for filenames
const brandSlug = path.basename(path.resolve(outputDir, '..'));
const outHtml = path.join(outputDir, `${brandSlug}-brand-guidelines.html`);
fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(outHtml, html, 'utf-8');
console.log(`HTML brand guidelines written to: ${outHtml}`);
