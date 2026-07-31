#!/usr/bin/env node
/**
 * generate-brand-guidelines-pdf.js
 *
 * Extends a brand's Quick Sheet PDF with additional pages showing all
 * resolved brand tokens: colors with swatches, typography, voice & tone,
 * content preferences, accessibility results, and unspecified tokens.
 */

const fs = require('fs');
const path = require('path');
const { PDFDocument, rgb, StandardFonts } = require('pdf-lib');

const args = process.argv.slice(2);
function getArg(name) {
  const idx = args.indexOf(`--${name}`);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : null;
}

const tokensPath = getArg('tokens');
const quicksheetPath = getArg('quicksheet');
const outputPath = getArg('output');

if (!tokensPath || !quicksheetPath || !outputPath) {
  console.error('Usage: node generate-brand-guidelines-pdf.js --tokens <path> --quicksheet <path> --output <path>');
  process.exit(1);
}

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  return { r: parseInt(h.substring(0, 2), 16) / 255, g: parseInt(h.substring(2, 4), 16) / 255, b: parseInt(h.substring(4, 6), 16) / 255 };
}
function luminance(hex) { const { r, g, b } = hexToRgb(hex); return 0.299 * r + 0.587 * g + 0.114 * b; }
function textColorForBg(hex) { return luminance(hex) > 0.5 ? rgb(0.12, 0.12, 0.12) : rgb(1, 1, 1); }

const PAGE_W = 612;
const PAGE_H = 792;
const ML = 54;
const MR = 54;
const COL_W = PAGE_W - ML - MR;
const HEADER_H = 44;
const FOOTER_Y = 36;

let B = { primary: '#2F6869', tertiary: '#003865', accent: '#DEFF00', panelBg: '#E8F4F4', ltGray: '#F0F0F0' };

class PageBuilder {
  constructor(doc, fonts, tokens) {
    this.doc = doc;
    this.fonts = fonts;
    this.tokens = tokens;
    this.page = null;
    this.y = 0;
    this.pageNum = 1;
    this.pageTitle = '';
    B.primary = tokens.color?.brand?.primary?.$value || '#333333';
    B.tertiary = tokens.color?.brand?.tertiary?.$value || '#666666';
    B.accent = tokens.color?.brand?.accent?.$value || '#0066CC';
    // Derive panel background as a very light tint of primary
    const pRgb = hexToRgb(B.primary);
    B.panelBg = `#${Math.round(pRgb.r * 255 * 0.1 + 240).toString(16).padStart(2,'0')}${Math.round(pRgb.g * 255 * 0.1 + 240).toString(16).padStart(2,'0')}${Math.round(pRgb.b * 255 * 0.1 + 240).toString(16).padStart(2,'0')}`;
  }

  newPage(title = '') {
    if (this.page) this.drawFooter();
    this.page = this.doc.addPage([PAGE_W, PAGE_H]);
    this.pageNum++;
    this.pageTitle = title;
    this._drawHeader(title);
    this.y = PAGE_H - HEADER_H - 26;
    return this;
  }

  _drawHeader(title) {
    const nc = hexToRgb(B.tertiary);
    this.page.drawRectangle({ x: 0, y: PAGE_H - HEADER_H, width: PAGE_W, height: HEADER_H, color: rgb(nc.r, nc.g, nc.b) });
    const tc = hexToRgb(B.primary);
    this.page.drawRectangle({ x: 0, y: PAGE_H - HEADER_H - 3, width: PAGE_W, height: 3, color: rgb(tc.r, tc.g, tc.b) });
    const vc = hexToRgb(B.accent);
    const bn = this.tokens.company?.name || 'Brand';
    const bnW = this.fonts.bold.widthOfTextAtSize(bn.toUpperCase(), 13);
    this.page.drawText(bn.toUpperCase(), { x: ML, y: PAGE_H - HEADER_H + 15, size: 13, font: this.fonts.bold, color: rgb(1, 1, 1) });
    this.page.drawRectangle({ x: ML + bnW + 8, y: PAGE_H - HEADER_H + 17, width: 6, height: 6, color: rgb(vc.r, vc.g, vc.b) });
    if (title) {
      const tw = this.fonts.bold.widthOfTextAtSize(title.toUpperCase(), 8);
      this.page.drawText(title.toUpperCase(), { x: PAGE_W - MR - tw, y: PAGE_H - HEADER_H + 17, size: 8, font: this.fonts.bold, color: rgb(0.7, 0.75, 0.82) });
    }
  }

  drawFooter() {
    const tc = hexToRgb(B.primary);
    this.page.drawRectangle({ x: ML, y: FOOTER_Y, width: COL_W, height: 0.5, color: rgb(tc.r, tc.g, tc.b) });
    const bn = this.tokens.company?.name || 'Brand';
    this.page.drawText(`${bn} Brand Guidelines`, { x: ML, y: FOOTER_Y - 12, size: 7, font: this.fonts.regular, color: rgb(0.5, 0.5, 0.5) });
    const pn = String(this.pageNum);
    const pw = this.fonts.regular.widthOfTextAtSize(pn, 7);
    this.page.drawText(pn, { x: PAGE_W - MR - pw, y: FOOTER_Y - 12, size: 7, font: this.fonts.regular, color: rgb(0.5, 0.5, 0.5) });
  }

  ensureSpace(needed) {
    if (this.y - needed < FOOTER_Y + 20) {
      this.drawFooter();
      this.newPage(this.pageTitle);
      return true;
    }
    return false;
  }

  sectionTitle(text) {
    this.ensureSpace(36);
    this.y -= 8;
    const tc = hexToRgb(B.primary);
    this.page.drawRectangle({ x: ML, y: this.y - 3, width: 4, height: 18, color: rgb(tc.r, tc.g, tc.b) });
    this.page.drawText(text.toUpperCase(), { x: ML + 14, y: this.y, size: 12, font: this.fonts.bold, color: rgb(tc.r, tc.g, tc.b) });
    this.y -= 22;
    return this;
  }

  sectionBand(text, bgHex = B.primary) {
    this.ensureSpace(36);
    this.y -= 4;
    const c = hexToRgb(bgHex);
    const bandH = 26;
    this.page.drawRectangle({ x: ML, y: this.y - bandH + 8, width: COL_W, height: bandH, color: rgb(c.r, c.g, c.b) });
    const tc = textColorForBg(bgHex);
    this.page.drawText(text.toUpperCase(), { x: ML + 12, y: this.y - bandH + 16, size: 10, font: this.fonts.bold, color: tc });
    this.y -= bandH + 6;
    return this;
  }

  subsectionTitle(text) {
    this.ensureSpace(22);
    this.y -= 6;
    const nc = hexToRgb(B.tertiary);
    this.page.drawText(text, { x: ML, y: this.y, size: 9, font: this.fonts.bold, color: rgb(nc.r, nc.g, nc.b) });
    this.page.drawRectangle({ x: ML, y: this.y - 4, width: COL_W, height: 0.5, color: rgb(0.85, 0.85, 0.85) });
    this.y -= 14;
    return this;
  }

  text(str, { size = 8.5, font = 'regular', color = rgb(0.19, 0.19, 0.19), indent = 0, maxWidth = COL_W } = {}) {
    const f = this.fonts[font];
    const words = str.split(' ');
    let line = '';
    const lines = [];
    for (const word of words) {
      const test = line ? `${line} ${word}` : word;
      if (f.widthOfTextAtSize(test, size) > maxWidth - indent && line) { lines.push(line); line = word; }
      else line = test;
    }
    if (line) lines.push(line);
    for (const l of lines) {
      this.ensureSpace(size + 5);
      this.page.drawText(l, { x: ML + indent, y: this.y, size, font: f, color });
      this.y -= size + 5;
    }
    return this;
  }

  spacer(h = 10) { this.y -= h; return this; }

  drawPanel(height, bgHex = '#F5F7F8') {
    const c = hexToRgb(bgHex);
    this.page.drawRectangle({ x: ML - 8, y: this.y - height + 8, width: COL_W + 16, height, color: rgb(c.r, c.g, c.b) });
    return this;
  }

  // Branded tagline callout block
  drawCallout(text, bgHex = B.tertiary) {
    const c = hexToRgb(bgHex);
    const vc = hexToRgb(B.accent);
    const blockH = 60;
    this.ensureSpace(blockH + 10);
    this.y -= 6;
    // Background
    this.page.drawRectangle({ x: ML, y: this.y - blockH, width: COL_W, height: blockH, color: rgb(c.r, c.g, c.b) });
    // Volt accent bar left
    this.page.drawRectangle({ x: ML, y: this.y - blockH, width: 5, height: blockH, color: rgb(vc.r, vc.g, vc.b) });
    // Text centered
    const tc = textColorForBg(bgHex);
    const f = this.fonts.oblique;
    const textW = f.widthOfTextAtSize(text, 10);
    const textX = ML + (COL_W - textW) / 2;
    this.page.drawText(text, { x: Math.max(ML + 20, textX), y: this.y - blockH / 2 - 4, size: 10, font: f, color: tc });
    this.y -= blockH + 6;
    return this;
  }

  // Bottom-of-page brand stripe (fills remaining space attractively)
  drawBottomStripe() {
    const stripeH = Math.max(this.y - FOOTER_Y - 20, 0);
    if (stripeH < 30) return this;
    // Subtle teal gradient-like band at the bottom
    const tc = hexToRgb(B.primary);
    this.page.drawRectangle({
      x: 0, y: FOOTER_Y + 16,
      width: PAGE_W, height: Math.min(stripeH, 6),
      color: rgb(tc.r, tc.g, tc.b),
    });
    return this;
  }

  drawHeroSwatches(swatches) {
    const gap = 14;
    const count = swatches.length;
    const swatchW = (COL_W - gap * (count - 1)) / count;
    const swatchH = 80;
    this.ensureSpace(swatchH + 36);

    for (let i = 0; i < count; i++) {
      const s = swatches[i];
      const x = ML + i * (swatchW + gap);
      const c = hexToRgb(s.hex);
      this.page.drawRectangle({ x: x + 2, y: this.y - swatchH - 2, width: swatchW, height: swatchH, color: rgb(0.85, 0.85, 0.85) });
      this.page.drawRectangle({ x, y: this.y - swatchH, width: swatchW, height: swatchH, color: rgb(c.r, c.g, c.b) });
      if (luminance(s.hex) > 0.85) this.page.drawRectangle({ x, y: this.y - swatchH, width: swatchW, height: swatchH, borderColor: rgb(0.82, 0.82, 0.82), borderWidth: 0.75, color: rgb(c.r, c.g, c.b) });
      const tc = textColorForBg(s.hex);
      this.page.drawText(s.hex.toUpperCase(), { x: x + 10, y: this.y - swatchH + 10, size: 10, font: this.fonts.monoBold, color: tc });
      // Name inside top-right
      this.page.drawText(s.label.toUpperCase(), { x: x + 10, y: this.y - 14, size: 8, font: this.fonts.bold, color: tc });
      // Description below swatch
      if (s.desc) this.page.drawText(s.desc, { x, y: this.y - swatchH - 12, size: 7, font: this.fonts.regular, color: rgb(0.4, 0.4, 0.4) });
    }
    this.y -= swatchH + 22;
    return this;
  }

  drawSwatchRow(swatches, { swatchH = 36, cols = null } = {}) {
    const count = swatches.length;
    const maxCols = cols || Math.min(count, 6);
    const gap = 8;
    const swatchW = Math.min(78, (COL_W - gap * (maxCols - 1)) / maxCols);

    for (let i = 0; i < count; i += maxCols) {
      const row = swatches.slice(i, i + maxCols);
      this.ensureSpace(swatchH + 28);
      for (let j = 0; j < row.length; j++) {
        const s = row[j];
        const x = ML + j * (swatchW + gap);
        const c = hexToRgb(s.hex);
        this.page.drawRectangle({ x: x + 1, y: this.y - swatchH - 1, width: swatchW, height: swatchH, color: rgb(0.88, 0.88, 0.88) });
        this.page.drawRectangle({ x, y: this.y - swatchH, width: swatchW, height: swatchH, color: rgb(c.r, c.g, c.b) });
        if (luminance(s.hex) > 0.85) this.page.drawRectangle({ x, y: this.y - swatchH, width: swatchW, height: swatchH, borderColor: rgb(0.82, 0.82, 0.82), borderWidth: 0.75, color: rgb(c.r, c.g, c.b) });
        const tc = textColorForBg(s.hex);
        this.page.drawText(s.hex.toUpperCase(), { x: x + 4, y: this.y - swatchH + 5, size: 6, font: this.fonts.monoBold, color: tc });
        if (s.label) this.page.drawText(s.label, { x, y: this.y - swatchH - 10, size: 6.5, font: this.fonts.bold, color: rgb(0.15, 0.15, 0.15) });
        if (s.desc) this.page.drawText(s.desc, { x, y: this.y - swatchH - 19, size: 5.5, font: this.fonts.regular, color: rgb(0.45, 0.45, 0.45) });
      }
      this.y -= swatchH + 26;
    }
    return this;
  }

  drawSwatchStrip(swatches, { swatchH = 24, cols = 6 } = {}) {
    const gap = 4;
    const swatchW = (COL_W - gap * (cols - 1)) / cols;
    for (let i = 0; i < swatches.length; i += cols) {
      const row = swatches.slice(i, i + cols);
      this.ensureSpace(swatchH + 10);
      for (let j = 0; j < row.length; j++) {
        const s = row[j];
        const x = ML + j * (swatchW + gap);
        const c = hexToRgb(s.hex);
        this.page.drawRectangle({ x, y: this.y - swatchH, width: swatchW, height: swatchH, color: rgb(c.r, c.g, c.b) });
        if (luminance(s.hex) > 0.85) this.page.drawRectangle({ x, y: this.y - swatchH, width: swatchW, height: swatchH, borderColor: rgb(0.82, 0.82, 0.82), borderWidth: 0.5, color: rgb(c.r, c.g, c.b) });
        const tc = textColorForBg(s.hex);
        this.page.drawText(s.label || '', { x: x + 4, y: this.y - 10, size: 5.5, font: this.fonts.bold, color: tc });
        this.page.drawText(s.hex.toUpperCase(), { x: x + 4, y: this.y - swatchH + 4, size: 5.5, font: this.fonts.mono, color: tc });
      }
      this.y -= swatchH + 6;
    }
    return this;
  }

  drawKeyValue(pairs, { labelWidth = 130, alternateRows = true } = {}) {
    for (let idx = 0; idx < pairs.length; idx++) {
      const [key, value] = pairs[idx];
      const valStr = String(value || '—');
      const maxValW = COL_W - labelWidth - 10;
      const words = valStr.split(' ');
      let line = '';
      const lines = [];
      for (const word of words) {
        const test = line ? `${line} ${word}` : word;
        if (this.fonts.regular.widthOfTextAtSize(test, 8) > maxValW && line) { lines.push(line); line = word; }
        else line = test;
      }
      if (line) lines.push(line);
      const rh = Math.max(lines.length, 1) * 13 + 3;
      this.ensureSpace(rh);
      if (alternateRows && idx % 2 === 0) {
        this.page.drawRectangle({ x: ML - 4, y: this.y - rh + 12, width: COL_W + 8, height: rh, color: rgb(0.96, 0.97, 0.97) });
      }
      this.page.drawText(key, { x: ML, y: this.y, size: 8, font: this.fonts.bold, color: rgb(0.2, 0.2, 0.2) });
      for (let i = 0; i < lines.length; i++) {
        this.page.drawText(lines[i], { x: ML + labelWidth, y: this.y - i * 13, size: 8, font: this.fonts.regular, color: rgb(0.25, 0.25, 0.25) });
      }
      this.y -= rh;
    }
    return this;
  }

  drawPreferenceTable(prefs, title) {
    if (!prefs || Object.keys(prefs).length === 0) return this;
    const validEntries = Object.entries(prefs).filter(([, v]) => v !== null);
    const nullEntries = Object.entries(prefs).filter(([, v]) => v === null);
    if (validEntries.length === 0 && nullEntries.length === 0) return this;

    this.subsectionTitle(title);
    if (validEntries.length > 0) {
      const colW = COL_W / 2;
      for (let i = 0; i < validEntries.length; i += 2) {
        this.ensureSpace(14);
        if (Math.floor(i / 2) % 2 === 0) this.page.drawRectangle({ x: ML - 4, y: this.y - 3, width: COL_W + 8, height: 13, color: rgb(0.96, 0.97, 0.97) });
        for (let j = 0; j < 2 && i + j < validEntries.length; j++) {
          const [key, val] = validEntries[i + j];
          const x = ML + j * colW;
          this.page.drawText(key, { x, y: this.y, size: 7, font: this.fonts.bold, color: rgb(0.3, 0.3, 0.3) });
          this.page.drawText(String(val), { x: x + 110, y: this.y, size: 7, font: this.fonts.regular, color: rgb(0.2, 0.2, 0.2) });
        }
        this.y -= 13;
      }
    }
    if (nullEntries.length > 0) {
      this.spacer(2);
      this.text(`Not specified: ${nullEntries.map(([k]) => k).join(', ')}`, { size: 6, color: rgb(0.6, 0.6, 0.6), font: 'oblique' });
    }
    this.spacer(4);
    return this;
  }
}

function collectUnspecified(tokens) {
  const inferred = [], derived = [], defaults = [];
  function walkColors(obj, prefix) {
    for (const [k, v] of Object.entries(obj)) {
      const path = prefix ? `${prefix}.${k}` : k;
      if (v && v.$value && v.$description && v.$description.includes('inferred')) inferred.push({ token: `color.${path}`, value: v.$value, desc: v.$description });
      else if (v && v.$source === 'derived') derived.push({ token: `color.${path}`, value: v.$value });
      else if (v && typeof v === 'object' && !v.$value) walkColors(v, path);
    }
  }
  if (tokens.color) walkColors(tokens.color, '');
  if (tokens.color?.derivative) {
    for (const [family, shades] of Object.entries(tokens.color.derivative))
      for (const [shade, val] of Object.entries(shades))
        derived.push({ token: `color.derivative.${family}.${shade}`, value: val.$value, desc: val.$description });
  }
  if (tokens.preference) {
    for (const [cat, prefs] of Object.entries(tokens.preference)) {
      if (cat === 'heading') continue;
      for (const [key, val] of Object.entries(prefs)) defaults.push({ token: `preference.${cat}.${key}`, value: val });
    }
  }
  return { inferred, derived, defaults };
}


async function main() {
  const tokensData = JSON.parse(fs.readFileSync(tokensPath, 'utf8'));
  const quicksheetBytes = fs.readFileSync(quicksheetPath);
  const quicksheetDoc = await PDFDocument.load(quicksheetBytes);
  const pdfDoc = await PDFDocument.create();
  const qsPages = await pdfDoc.copyPages(quicksheetDoc, quicksheetDoc.getPageIndices());
  for (const p of qsPages) pdfDoc.addPage(p);

  const fonts = {
    regular: await pdfDoc.embedFont(StandardFonts.Helvetica),
    bold: await pdfDoc.embedFont(StandardFonts.HelveticaBold),
    oblique: await pdfDoc.embedFont(StandardFonts.HelveticaOblique),
    mono: await pdfDoc.embedFont(StandardFonts.Courier),
    monoBold: await pdfDoc.embedFont(StandardFonts.CourierBold),
  };

  const pb = new PageBuilder(pdfDoc, fonts, tokensData);

  // ==========================================
  // PAGE 2: CORE COLOR PALETTE + EXTENDED + TEXT
  // ==========================================
  pb.newPage('Color System');
  pb.sectionTitle('Core Brand Palette');
  pb.spacer(2);

  const brandColors = Object.entries(tokensData.color.brand).map(([k, v]) => ({ hex: v.$value, label: k, desc: v.$description }));
  pb.drawHeroSwatches(brandColors);

  pb.spacer(2);
  pb.subsectionTitle('Extended Palette');
  const extColors = Object.entries(tokensData.color.extended).map(([k, v]) => ({ hex: v.$value, label: k, desc: v.$description }));
  pb.drawSwatchRow(extColors, { swatchH: 32, cols: 4 });

  pb.subsectionTitle('Text & Background Colors');
  const textColors = Object.entries(tokensData.color.text).map(([k, v]) => ({ hex: v.$value, label: k, desc: v.$description }));
  const bgColors = Object.entries(tokensData.color.background).map(([k, v]) => ({ hex: v.$value, label: k, desc: v.$description }));
  pb.drawSwatchRow([...textColors, ...bgColors], { swatchH: 28, cols: 7 });

  pb.drawFooter();

  // ==========================================
  // PAGE 3: FUNCTIONAL + HEADING + DERIVATIVES
  // ==========================================
  pb.newPage('Color System');
  pb.sectionTitle('Functional & Semantic Colors');
  pb.spacer(2);

  pb.subsectionTitle('Border & Link Colors');
  const borderColors = Object.entries(tokensData.color.border).map(([k, v]) => ({ hex: v.$value, label: k, desc: v.$description }));
  const linkColors = Object.entries(tokensData.color.link).map(([k, v]) => ({ hex: v.$value, label: k, desc: v.$description }));
  pb.drawSwatchRow([...borderColors, ...linkColors], { swatchH: 28, cols: 5 });

  pb.subsectionTitle('Status Colors');
  const statusColors = Object.entries(tokensData.color.status).map(([k, v]) => ({ hex: v.$value, label: k, desc: v.$description }));
  pb.drawSwatchRow(statusColors, { swatchH: 28 });

  pb.subsectionTitle('Heading Color Hierarchy');
  const headingColors = Object.entries(tokensData.color.heading).map(([k, v]) => ({ hex: v.$value, label: k, desc: v.$source === 'derived' ? 'derived' : 'explicit' }));
  pb.drawSwatchStrip(headingColors);

  pb.spacer(4);
  pb.sectionTitle('Derivative Palettes');
  pb.spacer(2);

  for (const family of ['primary', 'accent', 'tertiary']) {
    const derivs = tokensData.color.derivative?.[family];
    if (!derivs) continue;
    const label = family.charAt(0).toUpperCase() + family.slice(1);
    const baseHex = tokensData.color.brand[family]?.$value || '#000';
    pb.text(`${label} (${baseHex})`, { size: 7.5, font: 'bold', color: rgb(0.25, 0.25, 0.25) });
    pb.spacer(1);
    const swatches = [{ hex: baseHex, label: 'base' }];
    for (const [shade, val] of Object.entries(derivs)) swatches.push({ hex: val.$value, label: shade });
    pb.drawSwatchStrip(swatches);
  }

  // Use remaining space for a color usage note
  pb.spacer(10);
  const primaryName = tokensData.color?.brand?.primary?.$description || 'Primary';
  const tertiaryName = tokensData.color?.brand?.tertiary?.$description || 'Tertiary';
  const accentName = tokensData.color?.brand?.accent?.$description || 'Accent';
  pb.drawCallout(`${primaryName} leads. ${tertiaryName} supports. ${accentName} accents. Never use ${accentName} on white backgrounds.`, B.tertiary);

  pb.drawFooter();

  // ==========================================
  // PAGE 4: TYPOGRAPHY + TYPE SAMPLES
  // ==========================================
  pb.newPage('Typography');
  pb.sectionTitle('Font Families');
  pb.spacer(2);

  const typo = tokensData.typography;
  pb.drawKeyValue([
    ['Primary (headings & body)', typo.font.primary.$value],
    ['Secondary (display)', typo.font.secondary.$value],
    ['Fallback', typo.font.fallback.$value],
    ['Monospace', typo.font.monospace.$value],
  ]);

  pb.spacer(8);
  pb.subsectionTitle('Font Weights');
  pb.drawKeyValue([
    ['Light (300)', 'Subtle text, de-emphasized'],
    ['Body (400)', 'Standard body text'],
    ['Medium (500)', 'Semi-emphasized, sub-labels'],
    ['Heading (700)', 'Section headings'],
    ['Display (800)', 'Titles, hero text'],
  ]);

  pb.spacer(12);
  pb.sectionTitle('Type Samples');
  pb.text('Rendered in Helvetica — substitute Roboto/Montserrat in production', { size: 7, color: rgb(0.5, 0.5, 0.5), font: 'oblique' });
  pb.spacer(6);

  // Pale teal panel for type samples
  const sampleH = 155;
  pb.drawPanel(sampleH, B.panelBg);

  const pc = hexToRgb(B.primary);
  const nc = hexToRgb(B.tertiary);

  pb.ensureSpace(sampleH);
  const h1Desc = tokensData.color?.brand?.primary?.$description || 'Primary';
  const h2Desc = tokensData.color?.brand?.tertiary?.$description || 'Secondary';
  const h3Desc = tokensData.color?.brand?.primary?.$description || 'Primary';
  pb.page.drawText(`H1 Heading — ${h1Desc}`, { x: ML + 14, y: pb.y, size: 24, font: fonts.bold, color: rgb(pc.r, pc.g, pc.b) });
  pb.y -= 36;
  pb.page.drawText(`H2 Heading — ${h2Desc}`, { x: ML + 14, y: pb.y, size: 18, font: fonts.bold, color: rgb(nc.r, nc.g, nc.b) });
  pb.y -= 28;
  pb.page.drawText(`H3 Heading — ${h3Desc}`, { x: ML + 14, y: pb.y, size: 13, font: fonts.bold, color: rgb(pc.r, pc.g, pc.b) });
  pb.y -= 22;
  pb.page.drawText('Body text — Roboto Regular 400. The quick brown fox jumps over the lazy dog.', { x: ML + 14, y: pb.y, size: 10, font: fonts.regular, color: rgb(0.19, 0.19, 0.19) });
  pb.y -= 17;
  pb.page.drawText('Subtle text — captions, muted labels, secondary information.', { x: ML + 14, y: pb.y, size: 8.5, font: fonts.regular, color: rgb(0.5, 0.5, 0.5) });
  pb.y -= 15;
  pb.page.drawText('Monospace: Courier New — code snippets, technical content', { x: ML + 14, y: pb.y, size: 8.5, font: fonts.mono, color: rgb(0.19, 0.19, 0.19) });
  pb.y -= 18;

  // Fill bottom with tagline callout
  pb.spacer(10);
  pb.drawCallout(`"${tokensData.company.tagline}"`, B.tertiary);

  pb.drawFooter();

  // ==========================================
  // PAGE 5: VOICE & TONE + COMPANY INFO
  // ==========================================
  pb.newPage('Voice & Company');
  pb.sectionTitle('Voice & Tone');
  pb.spacer(2);

  const voice = tokensData.voice;
  pb.drawKeyValue([
    ['Tone', voice.tone],
    ['Perspective', voice.perspective],
    ['Formality', voice.formality],
    ['Avoidance', voice.avoidance],
  ], { labelWidth: 85 });

  pb.spacer(14);
  pb.sectionBand('Company Information', B.tertiary);
  pb.spacer(2);

  const co = tokensData.company;
  pb.drawKeyValue([
    ['Name', co.name],
    ['Legal Name', co.legalName],
    ['Tagline', co.tagline],
    ['Address', co.address],
    ['Phone', co.phone],
    ['Email', co.email],
    ['Website', co.website],
  ]);

  pb.spacer(12);
  pb.sectionTitle('Content Preferences');
  pb.spacer(2);

  const prefs = tokensData.preference;
  pb.drawPreferenceTable(prefs.docs, 'Documents');
  pb.drawPreferenceTable(prefs.slides, 'Slides');

  // Heading strategy
  pb.subsectionTitle('Heading Strategy');
  pb.drawKeyValue([
    ['Color Strategy', prefs.heading.colorStrategy],
    ['Weight Progression', prefs.heading.weightProgression],
  ]);

  // Compact note for all-null categories
  const nullCategories = [];
  for (const [cat, catPrefs] of Object.entries(prefs)) {
    if (cat === 'heading' || cat === 'docs' || cat === 'slides') continue;
    const allNull = Object.values(catPrefs).every(v => v === null);
    if (allNull) nullCategories.push(cat);
  }
  if (nullCategories.length > 0) {
    pb.spacer(6);
    pb.text(`Awaiting brand specification: ${nullCategories.join(', ')}`, { size: 7, color: rgb(0.5, 0.5, 0.5), font: 'oblique' });
  }

  pb.drawFooter();

  // ==========================================
  // PAGE 6: ACCESSIBILITY
  // ==========================================
  pb.newPage('Accessibility');

  pb.sectionTitle('Accessibility Standards');
  pb.spacer(4);

  const a11y = tokensData.accessibility;

  // Standards in a teal panel
  const stdPanelH = 50;
  pb.drawPanel(stdPanelH, B.panelBg);
  pb.ensureSpace(stdPanelH);
  pb.page.drawText('WCAG Compliance Targets', { x: ML + 12, y: pb.y, size: 9, font: fonts.bold, color: rgb(0.2, 0.2, 0.2) });
  pb.y -= 18;
  const tc2 = hexToRgb(B.primary);
  pb.page.drawText(`Text Contrast: ${a11y.textContrast}`, { x: ML + 12, y: pb.y, size: 10, font: fonts.bold, color: rgb(tc2.r, tc2.g, tc2.b) });
  pb.page.drawText(`UI Contrast: ${a11y.uiContrast}`, { x: ML + 200, y: pb.y, size: 10, font: fonts.bold, color: rgb(tc2.r, tc2.g, tc2.b) });
  pb.y -= 24;

  pb.spacer(8);
  pb.subsectionTitle('Contrast Validation Results');
  pb.spacer(2);

  for (let ci = 0; ci < a11y.computed.length; ci++) {
    const check = a11y.computed[ci];
    const passed = check.level !== 'fail';
    pb.ensureSpace(18);
    if (ci % 2 === 0) pb.page.drawRectangle({ x: ML - 4, y: pb.y - 4, width: COL_W + 8, height: 16, color: rgb(0.96, 0.97, 0.97) });

    const badgeColor = passed ? rgb(0.12, 0.49, 0.2) : rgb(0.8, 0.1, 0.1);
    const badgeBg = passed ? rgb(0.9, 0.96, 0.91) : rgb(0.98, 0.91, 0.91);
    pb.page.drawRectangle({ x: ML, y: pb.y - 3, width: 30, height: 14, color: badgeBg });
    pb.page.drawText(passed ? 'PASS' : 'FAIL', { x: ML + 4, y: pb.y, size: 7, font: fonts.monoBold, color: badgeColor });
    pb.page.drawText(`${check.foreground} on ${check.background}`, { x: ML + 40, y: pb.y, size: 7.5, font: fonts.regular, color: rgb(0.2, 0.2, 0.2) });
    const rt = `${check.ratio}:1 (${check.level})`;
    const rw = fonts.monoBold.widthOfTextAtSize(rt, 7);
    pb.page.drawText(rt, { x: PAGE_W - MR - rw, y: pb.y, size: 7, font: fonts.monoBold, color: badgeColor });
    pb.y -= 17;
  }

  // Use remaining space for color swatch contrast examples
  pb.spacer(16);
  pb.subsectionTitle('Key Color Pairings');
  pb.spacer(4);

  // Show a few key pairings as visual examples
  const pPairName = tokensData.color?.brand?.primary?.$description || 'Primary';
  const tPairName = tokensData.color?.brand?.tertiary?.$description || 'Tertiary';
  const bodyHex = tokensData.color?.text?.default?.$value || '#303030';
  const pairings = [
    { fg: B.primary, bg: '#FFFFFF', label: `${pPairName} on White` },
    { fg: '#FFFFFF', bg: B.primary, label: `White on ${pPairName}` },
    { fg: '#FFFFFF', bg: B.tertiary, label: `White on ${tPairName}` },
    { fg: bodyHex, bg: '#FFFFFF', label: 'Body on White' },
  ];
  const pairW = (COL_W - 12 * (pairings.length - 1)) / pairings.length;
  const pairH = 50;
  pb.ensureSpace(pairH + 20);

  for (let pi = 0; pi < pairings.length; pi++) {
    const p = pairings[pi];
    const x = ML + pi * (pairW + 12);
    const bgc = hexToRgb(p.bg);
    const fgc = hexToRgb(p.fg);

    // Background
    pb.page.drawRectangle({ x, y: pb.y - pairH, width: pairW, height: pairH, color: rgb(bgc.r, bgc.g, bgc.b) });
    if (luminance(p.bg) > 0.85) {
      pb.page.drawRectangle({ x, y: pb.y - pairH, width: pairW, height: pairH, borderColor: rgb(0.82, 0.82, 0.82), borderWidth: 0.75, color: rgb(bgc.r, bgc.g, bgc.b) });
    }
    // Sample text
    pb.page.drawText('Aa', { x: x + pairW / 2 - 10, y: pb.y - pairH / 2 - 5, size: 18, font: fonts.bold, color: rgb(fgc.r, fgc.g, fgc.b) });
    // Label
    pb.page.drawText(p.label, { x, y: pb.y - pairH - 12, size: 6.5, font: fonts.bold, color: rgb(0.3, 0.3, 0.3) });
  }
  pb.y -= pairH + 22;

  pb.drawFooter();

  // ==========================================
  // PAGE 7: COVERAGE + TOKEN PROVENANCE
  // ==========================================
  pb.newPage('Token Reference');

  pb.sectionBand('Coverage Summary', B.primary);
  pb.spacer(2);
  const cov = tokensData.$generated.coverage;

  // Coverage as a visual bar + stats
  const covPct = cov.percent / 100;
  const barW = COL_W - 140;
  const barH = 16;
  const barX = ML + 130;
  const barY = pb.y - barH / 2 - 2;

  // Background bar
  pb.page.drawRectangle({ x: barX, y: barY, width: barW, height: barH, color: rgb(0.9, 0.9, 0.9) });
  // Filled portion
  const tc = hexToRgb(B.primary);
  pb.page.drawRectangle({ x: barX, y: barY, width: barW * covPct, height: barH, color: rgb(tc.r, tc.g, tc.b) });
  // Percentage text
  pb.page.drawText(`${cov.percent}%`, { x: barX + barW * covPct + 6, y: barY + 4, size: 9, font: fonts.bold, color: rgb(tc.r, tc.g, tc.b) });
  pb.page.drawText('Token Coverage', { x: ML, y: barY + 4, size: 9, font: fonts.bold, color: rgb(0.2, 0.2, 0.2) });
  pb.y -= barH + 14;

  pb.drawKeyValue([
    ['Total Tokens', cov.total],
    ['Defined', cov.defined],
    ['Derived', cov.derived],
    ['Missing', cov.missing],
  ]);

  pb.spacer(14);
  pb.sectionTitle('Token Provenance');
  pb.spacer(2);

  const { inferred, derived, defaults } = collectUnspecified(tokensData);

  pb.subsectionTitle(`Inferred Tokens (${inferred.length})`);
  pb.text('Estimated from palette, not from source materials', { size: 6.5, color: rgb(0.55, 0.55, 0.55), font: 'oblique' });
  if (inferred.length === 0) pb.text('None', { size: 7 });
  for (const t of inferred) { pb.ensureSpace(11); pb.page.drawText(`${t.token}: ${t.value}`, { x: ML + 8, y: pb.y, size: 6.5, font: fonts.mono, color: rgb(0.3, 0.3, 0.3) }); pb.y -= 10; }

  pb.spacer(6);
  pb.subsectionTitle(`Derived Tokens (${derived.length})`);
  pb.text('Computed by parser from core palette', { size: 6.5, color: rgb(0.55, 0.55, 0.55), font: 'oblique' });

  // Two-column derived
  const dpc = Math.ceil(derived.length / 2);
  const colW2 = COL_W / 2;
  for (let i = 0; i < dpc; i++) {
    pb.ensureSpace(10);
    if (i % 3 === 0) pb.page.drawRectangle({ x: ML - 2, y: pb.y - 2, width: COL_W + 4, height: 10, color: rgb(0.97, 0.97, 0.97) });
    const t1 = derived[i];
    if (t1) { const d = t1.desc ? ` (${t1.desc})` : ''; pb.page.drawText(`${t1.token}: ${t1.value}${d}`, { x: ML + 4, y: pb.y, size: 5.5, font: fonts.mono, color: rgb(0.35, 0.35, 0.35) }); }
    const t2 = derived[i + dpc];
    if (t2) { const d = t2.desc ? ` (${t2.desc})` : ''; pb.page.drawText(`${t2.token}: ${t2.value}${d}`, { x: ML + colW2 + 4, y: pb.y, size: 5.5, font: fonts.mono, color: rgb(0.35, 0.35, 0.35) }); }
    pb.y -= 9;
  }

  pb.spacer(6);
  pb.subsectionTitle(`Default Preferences (${defaults.length})`);
  pb.text('Not explicitly set by brand owner', { size: 6.5, color: rgb(0.55, 0.55, 0.55), font: 'oblique' });

  const defPC = Math.ceil(defaults.length / 2);
  for (let i = 0; i < defPC; i++) {
    pb.ensureSpace(10);
    if (i % 3 === 0) pb.page.drawRectangle({ x: ML - 2, y: pb.y - 2, width: COL_W + 4, height: 10, color: rgb(0.97, 0.97, 0.97) });
    const t1 = defaults[i];
    if (t1) pb.page.drawText(`${t1.token} = ${t1.value}`, { x: ML + 4, y: pb.y, size: 5.5, font: fonts.mono, color: rgb(0.35, 0.35, 0.35) });
    const t2 = defaults[i + defPC];
    if (t2) pb.page.drawText(`${t2.token} = ${t2.value}`, { x: ML + colW2 + 4, y: pb.y, size: 5.5, font: fonts.mono, color: rgb(0.35, 0.35, 0.35) });
    pb.y -= 9;
  }

  pb.drawFooter();

  const pdfBytes = await pdfDoc.save();
  fs.writeFileSync(outputPath, pdfBytes);
  console.log(`Brand guidelines PDF written to ${outputPath} (${pdfDoc.getPageCount()} pages, ${Math.round(pdfBytes.length / 1024)}KB)`);
}

main().catch(err => { console.error(err); process.exit(1); });
