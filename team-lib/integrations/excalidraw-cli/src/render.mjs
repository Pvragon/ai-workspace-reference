// Core render engine. Launches one headless Chromium, injects the prebuilt
// bundle, and renders one-or-many jobs in that single browser.
//
// A "job" is { name, kind: "scene"|"mermaid", input } where input is either an
// Excalidraw elements array / scene object (kind "scene") or a Mermaid string
// (kind "mermaid").
//
// Programmatic API (for chaining from doc-gen scripts):
//   import { renderScene, renderMermaid, renderJobs } from ".../src/render.mjs";
//   const { svg, png, excalidraw } = await renderScene(elementsArray, { png: true });
//   const { svg }                  = await renderMermaid(mermaidText);
import { chromium } from "playwright";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BUNDLE = path.join(__dirname, "..", "dist", "bundle.js");

const FN = {
  scene: "window.__renderScene",
  mermaid: "window.__renderMermaid",
};

/**
 * Render many jobs in a single browser launch (amortized cost).
 * @param {Array<{name:string, kind:"scene"|"mermaid", input:any}>} jobs
 * @param {object} opts  render options forwarded to the browser functions
 * @returns {Promise<Array<{name, ok, svg?, png?, excalidraw?, count?, warnings?, error?}>>}
 */
export async function renderJobs(jobs, opts = {}) {
  if (!existsSync(BUNDLE)) {
    throw new Error(`Missing ${BUNDLE}. Run \`npm run build\` in excalidraw-cli first.`);
  }
  const bundle = readFileSync(BUNDLE, "utf8");
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent("<!doctype html><html><head></head><body></body></html>");
    await page.addScriptTag({ content: bundle });
    await page.waitForFunction("window.__mmdReady === true", null, { timeout: 20000 });

    const results = [];
    for (const job of jobs) {
      const fn = FN[job.kind];
      if (!fn) {
        results.push({ name: job.name, ok: false, error: `unknown job kind: ${job.kind}` });
        continue;
      }
      try {
        const out = await page.evaluate(
          async ({ fnName, input, o }) => {
            const f = fnName.split(".").reduce((acc, k) => acc[k], globalThis);
            return await f(input, o);
          },
          { fnName: fn, input: job.input, o: opts }
        );
        results.push({ name: job.name, ok: true, ...out });
      } catch (e) {
        results.push({ name: job.name, ok: false, error: String(e?.message || e) });
      }
    }
    return results;
  } finally {
    await browser.close();
  }
}

/**
 * Render a single Excalidraw scene (elements array or scene object).
 * @returns {Promise<{svg, png, excalidraw, count, warnings}>}
 */
export async function renderScene(input, opts = {}) {
  const [r] = await renderJobs([{ name: "scene", kind: "scene", input }], opts);
  if (!r.ok) throw new Error(r.error);
  return r;
}

/**
 * Render a single Mermaid definition.
 * @returns {Promise<{svg, png, excalidraw, count, warnings}>}
 */
export async function renderMermaid(definition, opts = {}) {
  const [r] = await renderJobs([{ name: "diagram", kind: "mermaid", input: definition }], opts);
  if (!r.ok) throw new Error(r.error);
  return r;
}
