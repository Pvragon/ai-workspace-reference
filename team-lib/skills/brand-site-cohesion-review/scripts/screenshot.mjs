#!/usr/bin/env node
/**
 * screenshot.mjs — visual-check tool that ACTUALLY RENDERS in headless WSL2.
 *
 * WSL2 has no GPU device nodes (/dev/dri absent), so default headless Chromium
 * paints blank/black. Forcing SwiftShader (software GL) fixes it. Use this to
 * eyeball the real build instead of only DOM metrics.
 *
 * Usage:
 *   node scripts/screenshot.mjs <url> [widths=375,768,1280] [outDir=.playwright-mcp]
 *   pnpm shot http://localhost:3000/ 1280
 * Env: CHROME_PATH overrides the browser binary.
 */
import { chromium } from "playwright-core";
import { readdirSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const SWIFTSHADER = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--disable-gpu", "--no-sandbox"];

function findChrome() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) return process.env.CHROME_PATH;
  const base = resolve(process.env.HOME || "", ".cache/ms-playwright");
  const dirs = existsSync(base)
    ? readdirSync(base).filter((d) => /^chromium-\d+$/.test(d)).sort((a, b) => +b.split("-")[1] - +a.split("-")[1])
    : [];
  for (const d of dirs) {
    for (const rel of ["chrome-linux64/chrome", "chrome-linux/chrome"]) {
      const p = resolve(base, d, rel);
      if (existsSync(p)) return p;
    }
  }
  return undefined; // fall back to playwright's own resolution
}

const url = process.argv[2] || "http://localhost:3000/";
const widths = (process.argv[3] || "375,768,1280").split(",").map(Number);
const outDir = resolve(process.argv[4] || ".playwright-mcp");
const fullPage = process.env.FULL_PAGE === "1";

mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch({ executablePath: findChrome(), headless: true, args: SWIFTSHADER });
const tag = url.replace(/^https?:\/\//, "").replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "") || "page";
for (const w of widths) {
  const page = await browser.newPage({ viewport: { width: w, height: 900 }, deviceScaleFactor: 1 });
  await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(500);
  const path = resolve(outDir, `${tag}-${w}.png`);
  await page.screenshot({ path, fullPage });
  console.log(`✓ ${w}px → ${path}`);
  await page.close();
}
await browser.close();
