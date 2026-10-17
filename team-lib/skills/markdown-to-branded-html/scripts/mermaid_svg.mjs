#!/usr/bin/env node
// ---
// mermaid_svg.mjs — render .mmd files to inline-ready SVG strings, each with a
// unique mermaid render id so several can coexist in one HTML page.
// Usage: node mermaid_svg.mjs <outdir> <in1.mmd> [in2.mmd ...]
// Derived from my-lib/executions/mermaid_png.mjs (same vendored chromium+mermaid).
// ---
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const CLI = process.env.HOME + '/ai-workspace/team-lib/integrations/excalidraw-cli/node_modules';
const require = createRequire(CLI + '/anchor.cjs');
const { chromium } = require('playwright');
const MERMAID = CLI + '/mermaid/dist/mermaid.min.js';
const [outDir, ...inFiles] = process.argv.slice(2);
if (!outDir || inFiles.length === 0) { console.error('usage: mermaid_svg.mjs <outdir> <in.mmd>...'); process.exit(1); }
fs.mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage();
await page.setContent('<div id="c"></div>');
await page.addScriptTag({ path: MERMAID });
let failures = 0;
for (const inFile of inFiles) {
  let code = fs.readFileSync(inFile, 'utf8').replace(/^---\n[\s\S]*?\n---\n/, '').trim();
  const id = 'm' + path.basename(inFile, '.mmd').replace(/[^a-zA-Z0-9]/g, '');
  const svg = await page.evaluate(async ({ src, rid }) => {
    mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose', flowchart: { htmlLabels: true, useMaxWidth: true } });
    try { const { svg } = await mermaid.render(rid, src); return svg; }
    catch (e) { return 'ERROR: ' + e.message; }
  }, { src: code, rid: id });
  if (svg.startsWith('ERROR:')) { console.error('FAIL', inFile, svg); failures++; continue; }
  fs.writeFileSync(path.join(outDir, path.basename(inFile, '.mmd') + '.svg'), svg);
  console.log('ok', path.basename(inFile, '.mmd'), svg.length, 'bytes');
}
await browser.close();
process.exit(failures ? 2 : 0);
