#!/usr/bin/env node
// ---
// template: execution
// version: 1.0.0
// summary: "Parses brand-guidelines.md into brand-tokens.json. Extracts token/value pairs from markdown tables, computes derivative colors, resolves heading fallbacks, validates accessibility contrast ratios."
// created: 2026-03-16
// last_updated: 2026-03-16
// maintainer: pvragon
// ---

/**
 * parse-guidelines.js
 *
 * Usage:
 *   node parse-guidelines.js --input <path/to/brand-guidelines.md> --output <path/to/brand-tokens.json>
 *   node parse-guidelines.js --input <path/to/brand-guidelines.md> --validate
 *   node parse-guidelines.js --input <path/to/brand-guidelines.md> --coverage
 */

const fs = require('fs');
const path = require('path');

// --- CLI argument parsing ---

const args = process.argv.slice(2);
const flags = {};
for (let i = 0; i < args.length; i++) {
  if (args[i].startsWith('--')) {
    const key = args[i].slice(2);
    const next = args[i + 1];
    if (next && !next.startsWith('--')) {
      flags[key] = next;
      i++;
    } else {
      flags[key] = true;
    }
  }
}

if (!flags.input) {
  console.error('Usage: node parse-guidelines.js --input <brand-guidelines.md> [--output <brand-tokens.json>] [--validate] [--coverage]');
  process.exit(1);
}

const inputPath = path.resolve(flags.input);
const outputPath = flags.output ? path.resolve(flags.output) : null;
const validateOnly = flags.validate === true;
const coverageOnly = flags.coverage === true;

if (!fs.existsSync(inputPath)) {
  console.error(`File not found: ${inputPath}`);
  process.exit(1);
}

const brandDir = path.dirname(inputPath);
const source = fs.readFileSync(inputPath, 'utf-8');

// --- Markdown table parser ---

/**
 * Extracts rows from markdown tables.
 * Returns array of objects keyed by header names (lowercased, trimmed).
 */
function parseTables(md) {
  const tables = [];
  const lines = md.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();
    // Detect table header row: starts and ends with |
    if (line.startsWith('|') && line.endsWith('|')) {
      const headerCells = line.split('|').slice(1, -1).map(c => c.trim().toLowerCase());
      // Next line should be separator (|---|---|)
      if (i + 1 < lines.length && /^\|[\s\-:|]+\|$/.test(lines[i + 1].trim())) {
        const rows = [];
        i += 2; // skip header + separator
        while (i < lines.length) {
          const rowLine = lines[i].trim();
          if (!rowLine.startsWith('|') || !rowLine.endsWith('|')) break;
          const cells = rowLine.split('|').slice(1, -1).map(c => c.trim());
          const row = {};
          headerCells.forEach((h, idx) => {
            row[h] = cells[idx] || '';
          });
          rows.push(row);
          i++;
        }
        tables.push({ headers: headerCells, rows });
        continue;
      }
    }
    i++;
  }
  return tables;
}

// --- Token extraction ---

/**
 * Extracts token path and value from a table row.
 * Token path is in backticks in the first column (token, field, attribute, or preference).
 */
function extractTokenPath(row) {
  const keyCol = row.token || row.field || row.attribute || row.preference || '';
  const match = keyCol.match(/`([^`]+)`/);
  return match ? match[1] : null;
}

function extractColorValue(row) {
  const hex = (row.hex || '').replace(/^#/, '').trim();
  if (!hex || hex.length < 3) return null;
  return `#${hex.toUpperCase()}`;
}

function extractSimpleValue(row) {
  return (row.value || '').trim() || null;
}

function extractLogoRow(row) {
  const file = (row.file || '').trim();
  if (!file) return null;
  const width = parseInt(row.width) || null;
  const height = parseInt(row.height) || null;
  return { file, width, height };
}

// --- Color utilities ---

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  return {
    r: parseInt(h.substring(0, 2), 16),
    g: parseInt(h.substring(2, 4), 16),
    b: parseInt(h.substring(4, 6), 16)
  };
}

function rgbToHex(r, g, b) {
  const clamp = v => Math.max(0, Math.min(255, Math.round(v)));
  return `#${[r, g, b].map(v => clamp(v).toString(16).padStart(2, '0')).join('').toUpperCase()}`;
}

function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h, s, l = (max + min) / 2;

  if (max === min) {
    h = s = 0;
  } else {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return { h: h * 360, s: s * 100, l: l * 100 };
}

function hslToRgb(h, s, l) {
  h /= 360; s /= 100; l /= 100;
  let r, g, b;

  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p, q, t) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1/6) return p + (q - p) * 6 * t;
      if (t < 1/2) return q;
      if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1/3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1/3);
  }
  return { r: r * 255, g: g * 255, b: b * 255 };
}

function adjustLightness(hex, percent) {
  const rgb = hexToRgb(hex);
  const hsl = rgbToHsl(rgb.r, rgb.g, rgb.b);
  hsl.l = Math.max(0, Math.min(100, hsl.l + percent));
  const newRgb = hslToRgb(hsl.h, hsl.s, hsl.l);
  return rgbToHex(newRgb.r, newRgb.g, newRgb.b);
}

/**
 * WCAG 2.1 relative luminance
 */
function relativeLuminance(hex) {
  const rgb = hexToRgb(hex);
  const [rs, gs, bs] = [rgb.r, rgb.g, rgb.b].map(c => {
    c = c / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

function contrastRatio(hex1, hex2) {
  const l1 = relativeLuminance(hex1);
  const l2 = relativeLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

function contrastLevel(ratio) {
  if (ratio >= 7) return 'AAA';
  if (ratio >= 4.5) return 'AA';
  if (ratio >= 3) return 'AA-large';
  return 'fail';
}

// --- Derivative color generation ---

function generateDerivatives(hex) {
  if (!hex) return null;
  return {
    tint1: { '$value': adjustLightness(hex, 15), '$type': 'color', '$description': '+25% lightness' },
    tint2: { '$value': adjustLightness(hex, 30), '$type': 'color', '$description': '+50% lightness' },
    tint3: { '$value': adjustLightness(hex, 45), '$type': 'color', '$description': '+75% lightness' },
    shade1: { '$value': adjustLightness(hex, -15), '$type': 'color', '$description': '-25% lightness' },
    shade2: { '$value': adjustLightness(hex, -30), '$type': 'color', '$description': '-50% lightness' }
  };
}

// --- Heading color resolution ---

function resolveHeadingColors(headingTokens, brandColors, strategy) {
  const resolved = {};
  const primary = headingTokens.h1 || brandColors.primary;
  const accent = headingTokens.h2 || brandColors.accent;

  // h1 and h2: explicit or fallback to brand colors
  resolved.h1 = { '$value': primary, '$type': 'color', '$source': headingTokens.h1 ? 'explicit' : 'fallback' };
  resolved.h2 = { '$value': accent, '$type': 'color', '$source': headingTokens.h2 ? 'explicit' : 'fallback' };

  // h3: explicit or falls back to h1
  resolved.h3 = {
    '$value': headingTokens.h3 || primary,
    '$type': 'color',
    '$source': headingTokens.h3 ? 'explicit' : 'fallback'
  };

  // h4-h6: explicit or derived from strategy
  const derivePrimary = primary ? adjustLightness(primary, 15) : null;
  const deriveAccent = accent ? adjustLightness(accent, 15) : null;

  const strategies = {
    'alternating': [derivePrimary, deriveAccent, primary],
    'primary-only': [derivePrimary, adjustLightness(primary || '#000000', 25), adjustLightness(primary || '#000000', 35)],
    'accent-only': [deriveAccent, adjustLightness(accent || '#000000', 25), adjustLightness(accent || '#000000', 35)],
    'gradient': [adjustLightness(primary || '#000000', 15), adjustLightness(primary || '#000000', 25), adjustLightness(primary || '#000000', 35)]
  };

  const pattern = strategies[strategy] || strategies['alternating'];

  ['h4', 'h5', 'h6'].forEach((level, idx) => {
    resolved[level] = {
      '$value': headingTokens[level] || pattern[idx],
      '$type': 'color',
      '$source': headingTokens[level] ? 'explicit' : 'derived'
    };
  });

  return resolved;
}

// --- Preference value conversion ---

function convertPreferenceValue(val) {
  if (val === 'yes' || val === 'true') return true;
  if (val === 'no' || val === 'false') return false;
  const num = Number(val);
  if (!isNaN(num) && val.trim() !== '') return num;
  // Strip backticks if present
  return val.replace(/^`|`$/g, '').trim();
}

// --- Main parsing logic ---

function parseGuidelines(source, brandDir) {
  const tables = parseTables(source);
  const tokens = {
    color: { brand: {}, text: {}, background: {}, border: {}, link: {}, status: {}, heading: {}, extended: {}, derivative: {} },
    typography: { font: {}, weight: {} },
    logo: {},
    company: {},
    voice: {},
    preference: { heading: {}, docs: {}, slides: {}, web: {}, social: {}, ads: {}, longform: {} },
    accessibility: {}
  };

  const coverage = { total: 0, defined: 0, derived: 0, missing: 0, missingRequired: [], missingOptional: [] };
  const headingExplicit = {};

  for (const table of tables) {
    for (const row of table.rows) {
      const tokenPath = extractTokenPath(row);
      if (!tokenPath) continue;

      coverage.total++;

      // --- Colors ---
      if (tokenPath.startsWith('color.')) {
        const hex = extractColorValue(row);
        const parts = tokenPath.split('.');
        const category = parts[1]; // brand, text, background, etc.
        const name = parts.slice(2).join('.');

        if (category === 'heading') {
          if (hex) headingExplicit[name] = hex;
        } else if (category === 'extended') {
          if (hex) {
            tokens.color.extended[name] = { '$value': hex, '$type': 'color', '$description': row.name || '' };
            coverage.defined++;
          } else {
            coverage.missing++;
            coverage.missingOptional.push(tokenPath);
          }
        } else if (tokens.color[category]) {
          tokens.color[category][name] = { '$value': hex, '$type': 'color', '$description': row.name || row.usage || '' };
          if (hex) coverage.defined++;
          else { coverage.missing++; coverage.missingOptional.push(tokenPath); }
        }
      }

      // --- Typography ---
      else if (tokenPath.startsWith('typography.')) {
        const val = extractSimpleValue(row);
        const parts = tokenPath.split('.');
        const category = parts[1]; // font or weight
        const name = parts[2];

        if (category === 'weight') {
          const numVal = val ? parseInt(val) : null;
          tokens.typography.weight[name] = { '$value': numVal, '$type': 'fontWeight' };
        } else {
          tokens.typography.font[name] = { '$value': val, '$type': 'fontFamily' };
        }
        if (val) coverage.defined++;
        else { coverage.missing++; coverage.missingOptional.push(tokenPath); }
      }

      // --- Logos ---
      else if (tokenPath.startsWith('logo.')) {
        const name = tokenPath.split('.')[1];
        const logoData = extractLogoRow(row);
        if (logoData) {
          const absPath = path.resolve(brandDir, logoData.file);
          tokens.logo[name] = {
            file: logoData.file,
            absolutePath: absPath,
            width: logoData.width,
            height: logoData.height
          };
          coverage.defined++;
        } else {
          tokens.logo[name] = { file: null, absolutePath: null, width: null, height: null };
          coverage.missing++;
          if (name === 'full') coverage.missingRequired.push(tokenPath);
          else coverage.missingOptional.push(tokenPath);
        }
      }

      // --- Company ---
      else if (tokenPath.startsWith('company.')) {
        const name = tokenPath.split('.')[1];
        const val = extractSimpleValue(row);
        tokens.company[name] = val;
        if (val) coverage.defined++;
        else { coverage.missing++; coverage.missingOptional.push(tokenPath); }
      }

      // --- Voice ---
      else if (tokenPath.startsWith('voice.')) {
        const name = tokenPath.split('.')[1];
        const val = extractSimpleValue(row);
        tokens.voice[name] = val;
        if (val) coverage.defined++;
        else { coverage.missing++; coverage.missingOptional.push(tokenPath); }
      }

      // --- Heading preferences ---
      else if (tokenPath.startsWith('heading.')) {
        const name = tokenPath.split('.')[1];
        const val = extractSimpleValue(row);
        tokens.preference.heading[name] = val ? convertPreferenceValue(val) : null;
        if (val) coverage.defined++;
        else { coverage.missing++; coverage.missingOptional.push(tokenPath); }
      }

      // --- Content preferences ---
      else if (tokenPath.match(/^(docs|slides|web|social|ads|longform)\./)) {
        const parts = tokenPath.split('.');
        const category = parts[0];
        const name = parts[1];
        const val = extractSimpleValue(row);
        if (!tokens.preference[category]) tokens.preference[category] = {};
        tokens.preference[category][name] = val ? convertPreferenceValue(val) : null;
        if (val) coverage.defined++;
        else { coverage.missing++; coverage.missingOptional.push(tokenPath); }
      }

      // --- Accessibility ---
      else if (tokenPath.startsWith('a11y.')) {
        const name = tokenPath.split('.')[1];
        const val = extractSimpleValue(row);
        tokens.accessibility[name] = val ? convertPreferenceValue(val) : null;
        if (val) coverage.defined++;
        else { coverage.missing++; coverage.missingOptional.push(tokenPath); }
      }
    }
  }

  // --- Resolve heading colors ---
  const brandColors = {
    primary: tokens.color.brand.primary?.$value,
    accent: tokens.color.brand.accent?.$value
  };
  const headingStrategy = tokens.preference.heading?.colorStrategy || 'alternating';
  tokens.color.heading = resolveHeadingColors(headingExplicit, brandColors, headingStrategy);
  coverage.derived += Object.values(tokens.color.heading).filter(h => h.$source === 'derived').length;

  // --- Generate derivatives ---
  const primaryHex = tokens.color.brand.primary?.$value;
  const accentHex = tokens.color.brand.accent?.$value;
  const tertiaryHex = tokens.color.brand.tertiary?.$value;

  tokens.color.derivative.primary = primaryHex ? generateDerivatives(primaryHex) : null;
  tokens.color.derivative.accent = accentHex ? generateDerivatives(accentHex) : null;
  tokens.color.derivative.tertiary = tertiaryHex ? generateDerivatives(tertiaryHex) : null;
  coverage.derived += (primaryHex ? 5 : 0) + (accentHex ? 5 : 0) + (tertiaryHex ? 5 : 0);

  // --- Compute accessibility ---
  const bgDefault = tokens.color.background.default?.$value || '#FFFFFF';
  const contrastPairs = [];

  const colorPairs = [
    ['color.brand.primary', tokens.color.brand.primary?.$value],
    ['color.brand.accent', tokens.color.brand.accent?.$value],
    ['color.text.default', tokens.color.text.default?.$value],
    ['color.text.subtle', tokens.color.text.subtle?.$value],
    ['color.heading.h1', tokens.color.heading.h1?.$value],
    ['color.heading.h2', tokens.color.heading.h2?.$value],
    ['color.link.default', tokens.color.link.default?.$value]
  ];

  for (const [name, fg] of colorPairs) {
    if (fg) {
      const ratio = Math.round(contrastRatio(fg, bgDefault) * 100) / 100;
      contrastPairs.push({
        foreground: name,
        background: 'color.background.default',
        ratio,
        level: contrastLevel(ratio)
      });
    }
  }

  // onPrimary on primary
  const onPrimary = tokens.color.text.onPrimary?.$value;
  if (onPrimary && primaryHex) {
    const ratio = Math.round(contrastRatio(onPrimary, primaryHex) * 100) / 100;
    contrastPairs.push({
      foreground: 'color.text.onPrimary',
      background: 'color.brand.primary',
      ratio,
      level: contrastLevel(ratio)
    });
  }

  tokens.accessibility.computed = contrastPairs;

  // --- Coverage stats ---
  coverage.percent = coverage.total > 0
    ? Math.round((coverage.defined / coverage.total) * 1000) / 10
    : 0;

  return { tokens, coverage };
}

// --- Output assembly ---

function buildOutput(tokens, coverage) {
  return {
    '$schema': 'brand-tokens-v1',
    '$generated': {
      from: 'brand-guidelines.md',
      by: 'parse-guidelines.js',
      at: new Date().toISOString(),
      guidelinesVersion: '1.1.0',
      coverage: {
        total: coverage.total,
        defined: coverage.defined,
        derived: coverage.derived,
        missing: coverage.missing,
        percent: coverage.percent
      }
    },
    ...tokens
  };
}

// --- Main ---

const { tokens, coverage } = parseGuidelines(source, brandDir);

if (coverageOnly) {
  console.log(`\nBrand Guidelines Coverage Report`);
  console.log(`================================`);
  console.log(`Tokens total:     ${coverage.total}`);
  console.log(`Tokens defined:   ${coverage.defined}`);
  console.log(`Tokens derived:   ${coverage.derived}`);
  console.log(`Tokens missing:   ${coverage.missing}`);
  console.log(`Coverage:         ${coverage.percent}%`);
  if (coverage.missingRequired.length > 0) {
    console.log(`\nMissing required:`);
    coverage.missingRequired.forEach(t => console.log(`  - ${t}`));
  }
  if (coverage.missingOptional.length > 0) {
    console.log(`\nMissing optional:`);
    coverage.missingOptional.forEach(t => console.log(`  - ${t}`));
  }
  process.exit(0);
}

if (validateOnly) {
  console.log(`\nValidation Report`);
  console.log(`=================`);
  console.log(`Coverage: ${coverage.defined}/${coverage.total} tokens (${coverage.percent}%)`);
  console.log(`Derived:  ${coverage.derived} tokens computed`);

  const a11yTarget = tokens.accessibility.textContrast || 'AA';
  const minRatio = a11yTarget === 'AAA' ? 7 : a11yTarget === 'AA' ? 4.5 : 0;
  const failures = (tokens.accessibility.computed || []).filter(c => c.ratio < minRatio);

  console.log(`\nAccessibility (target: ${a11yTarget}):`);
  for (const pair of tokens.accessibility.computed || []) {
    const status = pair.ratio >= minRatio ? 'PASS' : 'FAIL';
    console.log(`  ${status} ${pair.foreground} on ${pair.background}: ${pair.ratio}:1 (${pair.level})`);
  }

  if (failures.length > 0) {
    console.log(`\n⚠ ${failures.length} color combination(s) fail ${a11yTarget} contrast requirements`);
  } else {
    console.log(`\nAll color combinations pass ${a11yTarget} contrast requirements`);
  }

  if (coverage.missingRequired.length > 0) {
    console.log(`\nMissing required tokens:`);
    coverage.missingRequired.forEach(t => console.log(`  - ${t}`));
  }

  process.exit(failures.length > 0 ? 1 : 0);
}

// Default: generate output
const output = buildOutput(tokens, coverage);
const json = JSON.stringify(output, null, 2);

if (outputPath) {
  fs.writeFileSync(outputPath, json, 'utf-8');
  console.log(`brand-tokens.json written to ${outputPath}`);
  console.log(`Coverage: ${coverage.defined}/${coverage.total} tokens (${coverage.percent}%), ${coverage.derived} derived`);
  if (coverage.missingRequired.length > 0) {
    console.log(`Missing required: ${coverage.missingRequired.join(', ')}`);
  }
} else {
  process.stdout.write(json);
}
