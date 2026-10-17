#!/usr/bin/env node
// ---
// script: validate-brand-guide-html.js
// version: 1.0.0
// summary: Hard gate for generate-brand-guide-site — verifies a brand-guide.html
//          uses ONLY values from brand-tokens.json: every hex/rgb color must be a
//          token color, every font-family a token font (or CSS generic), external
//          resources limited to Google Fonts for token font families, and relative
//          asset paths must resolve on disk. Exit 0 = PASS, 1 = violations found.
// usage:   node validate-brand-guide-html.js --html <path> --tokens <path>
// created: 2026-07-13
// maintainer: pvragon
// ---
'use strict';

const fs = require('fs');
const path = require('path');

function parseArgs() {
  const args = process.argv.slice(2);
  const out = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--html') out.html = args[++i];
    else if (args[i] === '--tokens') out.tokens = args[++i];
  }
  if (!out.html || !out.tokens) {
    console.error('usage: validate-brand-guide-html.js --html <brand-guide.html> --tokens <brand-tokens.json>');
    process.exit(2);
  }
  return out;
}

// --- token extraction -------------------------------------------------------

function normalizeHex(hex) {
  let h = hex.replace('#', '').toUpperCase();
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  if (h.length === 8) h = h.slice(0, 6); // drop alpha channel
  return h.length === 6 ? h : null;
}

// Recursively collect every $value that looks like a hex color.
function collectTokenColors(node, acc) {
  if (node === null || typeof node !== 'object') return acc;
  if (typeof node.$value === 'string' && /^#?[0-9a-fA-F]{3,8}$/.test(node.$value.trim())) {
    const n = normalizeHex(node.$value.trim());
    if (n) acc.add(n);
  }
  for (const k of Object.keys(node)) {
    if (k.startsWith('$')) continue;
    collectTokenColors(node[k], acc);
  }
  return acc;
}

function collectTokenFonts(tokens) {
  const fonts = new Set();
  const fontNode = tokens.typography && tokens.typography.font;
  if (fontNode) {
    for (const k of Object.keys(fontNode)) {
      const v = fontNode[k] && fontNode[k].$value;
      if (typeof v === 'string' && v.trim()) fonts.add(v.trim().toLowerCase());
    }
  }
  return fonts;
}

const CSS_GENERIC_FONTS = new Set([
  'sans-serif', 'serif', 'monospace', 'cursive', 'fantasy',
  'system-ui', 'ui-sans-serif', 'ui-serif', 'ui-monospace', 'ui-rounded',
  'emoji', 'math', 'fangsong', 'inherit', 'initial', 'unset',
]);

const ALLOWED_EXTERNAL_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);

// --- html scanning ----------------------------------------------------------

function main() {
  const { html: htmlPath, tokens: tokensPath } = parseArgs();
  const html = fs.readFileSync(htmlPath, 'utf8');
  const tokens = JSON.parse(fs.readFileSync(tokensPath, 'utf8'));

  const allowedColors = collectTokenColors(tokens, new Set());
  const allowedFonts = collectTokenFonts(tokens);
  const violations = [];
  const stats = { hexChecked: 0, rgbChecked: 0, fontDecls: 0, resources: 0 };

  // Strip data: URIs before scanning — base64 payloads produce false hex matches.
  const scannable = html.replace(/data:[a-z/+.-]+;base64,[A-Za-z0-9+/=]+/g, 'data:STRIPPED');

  // 1. Hex colors. Word boundaries avoid matching ids/anchors; require a non-hex
  //    char (or start) before '#' and 3/6/8 hex digits not followed by more hex.
  const hexRe = /#([0-9a-fA-F]{3,8})\b/g;
  const seenBadHex = new Set();
  let m;
  while ((m = hexRe.exec(scannable)) !== null) {
    if (![3, 6, 8].includes(m[1].length)) continue;
    stats.hexChecked++;
    const n = normalizeHex(m[1]);
    if (n && !allowedColors.has(n) && !seenBadHex.has(n)) {
      seenBadHex.add(n);
      violations.push(`COLOR   #${n} not in brand-tokens.json`);
    }
  }

  // 2. rgb()/rgba() colors — alpha is free, the RGB triple must be a token color.
  const rgbRe = /rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/g;
  const seenBadRgb = new Set();
  while ((m = rgbRe.exec(scannable)) !== null) {
    stats.rgbChecked++;
    const hex = [m[1], m[2], m[3]]
      .map((c) => Number(c).toString(16).padStart(2, '0'))
      .join('')
      .toUpperCase();
    if (!allowedColors.has(hex) && !seenBadRgb.has(hex)) {
      seenBadRgb.add(hex);
      violations.push(`COLOR   rgb(${m[1]},${m[2]},${m[3]}) = #${hex} not in brand-tokens.json`);
    }
  }

  // 3. Font families.
  const ffRe = /font-family\s*:\s*([^;}]+)/g;
  const seenBadFont = new Set();
  while ((m = ffRe.exec(scannable)) !== null) {
    stats.fontDecls++;
    for (let fam of m[1].split(',')) {
      fam = fam.trim().replace(/^["']|["']$/g, '').trim().toLowerCase();
      if (!fam || fam.startsWith('var(')) continue;
      if (!allowedFonts.has(fam) && !CSS_GENERIC_FONTS.has(fam) && !seenBadFont.has(fam)) {
        seenBadFont.add(fam);
        violations.push(`FONT    "${fam}" not in brand-tokens.json typography.font.* (or CSS generic)`);
      }
    }
  }

  // 4. External resources — <img src>, <script src>, <link href>, @import, css url().
  const resRe = /(?:<(?:img|script|source|iframe)[^>]*\ssrc|<link[^>]*\shref)\s*=\s*["']([^"']+)["']|@import\s+(?:url\()?["']?([^"')\s]+)|url\(\s*["']?([^"')\s]+)/gi;
  while ((m = resRe.exec(scannable)) !== null) {
    const url = (m[1] || m[2] || m[3] || '').trim();
    if (!url || url.startsWith('data:') || url.startsWith('#')) continue;
    stats.resources++;
    if (/^https?:\/\//i.test(url)) {
      const host = url.replace(/^https?:\/\//i, '').split(/[/?#]/)[0].toLowerCase();
      if (!ALLOWED_EXTERNAL_HOSTS.has(host)) {
        violations.push(`EXTERN  ${url} — only ${[...ALLOWED_EXTERNAL_HOSTS].join(', ')} permitted`);
      } else if (host === 'fonts.googleapis.com') {
        // Every family requested from Google Fonts must be a token font.
        const famRe = /family=([^&:]+)/g;
        let fm;
        while ((fm = famRe.exec(url)) !== null) {
          const fam = decodeURIComponent(fm[1]).replace(/\+/g, ' ').trim().toLowerCase();
          if (!allowedFonts.has(fam)) {
            violations.push(`EXTERN  Google Fonts family "${fam}" not in brand-tokens.json`);
          }
        }
      }
    } else if (!/^(mailto:|tel:|javascript:)/i.test(url)) {
      const resolved = path.resolve(path.dirname(htmlPath), url);
      if (!fs.existsSync(resolved)) {
        violations.push(`ASSET   ${url} does not resolve (from ${path.dirname(htmlPath)})`);
      }
    }
  }

  // 5. Basic structure.
  if (!/<title>[^<]+<\/title>/i.test(html)) violations.push('STRUCT  missing <title>');
  if (!/<h1[\s>]/i.test(html)) violations.push('STRUCT  missing <h1>');
  if (!/<meta[^>]+viewport/i.test(html)) violations.push('STRUCT  missing viewport meta');

  // --- report ---
  console.log(`validate-brand-guide-html: ${path.basename(htmlPath)} vs ${path.basename(tokensPath)}`);
  console.log(`  token colors allowed: ${allowedColors.size} | token fonts: ${[...allowedFonts].join(', ') || '(none)'}`);
  console.log(`  scanned: ${stats.hexChecked} hex, ${stats.rgbChecked} rgb(), ${stats.fontDecls} font-family decls, ${stats.resources} resource refs`);
  if (violations.length === 0) {
    console.log('  PASS — every color and font traces to brand-tokens.json; file is self-contained.');
    process.exit(0);
  }
  console.log(`  FAIL — ${violations.length} violation(s):`);
  for (const v of violations) console.log(`    ${v}`);
  process.exit(1);
}

main();
