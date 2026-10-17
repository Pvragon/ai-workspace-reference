/**
 * Mermaid → Excalidraw preprocessing for the branded-doc pipeline.
 *
 * Replaces ```mermaid fenced code blocks in a markdown string with a standard
 * image reference (`![alt](abs-path)`) that the existing renderers already know
 * how to embed. Renders via the excalidraw-cli engine (headless Chromium), all
 * diagrams in a single browser launch.
 *
 * Default-on; the caller passes { enabled: false } to leave mermaid fences as-is.
 * A render failure throws (a broken diagram is a diagram-logic bug the author
 * must fix, not something to silently drop).
 */
const fs = require('fs');
const os = require('os');
const path = require('path');

// scripts/lib -> team-lib/integrations/excalidraw-cli/src/render.mjs (ESM; imported dynamically)
const CLI_DIR = path.resolve(__dirname, '../../../../integrations/excalidraw-cli');
const RENDER_MJS = path.join(CLI_DIR, 'src', 'render.mjs');

// Shown when the excalidraw-cli isn't installed on a fresh clone. The two setup
// steps (deps + the Chromium browser) aren't covered by a plain `git clone`.
const SETUP_HINT =
  `excalidraw-cli is not set up (needed to render \`\`\`mermaid diagrams). One-time setup:\n` +
  `  cd ${CLI_DIR} && npm install && npx playwright install chromium\n` +
  `Or pass --no-excalidraw (CLI) / { enabled: false } (API) to skip diagram rendering.`;

// Turn a low-level "not installed" failure into an actionable setup message.
function isSetupError(e) {
  const m = String(e && (e.message || e));
  return (
    e?.code === 'ERR_MODULE_NOT_FOUND' ||   // node_modules missing (playwright import)
    /Cannot find package/i.test(m) ||
    /Missing .*bundle\.js/i.test(m) ||       // postinstall build didn't run
    /Executable doesn'?t exist|playwright install/i.test(m) // chromium not downloaded
  );
}

// Fenced ```mermaid blocks (case-insensitive language tag).
const FENCE_RE = /^[ \t]*```[ \t]*mermaid[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*```[ \t]*$/gim;

/**
 * @param {string} md            markdown source
 * @param {object} opts
 * @param {boolean} [opts.enabled=true]   false = leave fences untouched
 * @param {"png"|"svg"} [opts.format="png"]  raster embeds everywhere; svg for vector targets
 * @param {string} [opts.assetsDir]       where to write rendered images (default: a temp dir)
 * @param {object} [opts.renderOpts={}]   forwarded to the excalidraw engine (dark, scale, font…)
 * @returns {Promise<{md, diagrams, count, skipped?, assetsDir?}>}
 */
async function preprocessMermaid(md, opts = {}) {
  const { enabled = true, format = 'png', renderOpts = {} } = opts;

  const fences = [];
  let m;
  FENCE_RE.lastIndex = 0;
  while ((m = FENCE_RE.exec(md)) !== null) {
    fences.push({ full: m[0], def: m[1], index: m.index });
  }

  if (!enabled) return { md, diagrams: [], count: fences.length, skipped: true };
  if (fences.length === 0) return { md, diagrams: [], count: 0 };

  // Fail fast + clear if the tool was never installed on this clone.
  if (!fs.existsSync(path.join(CLI_DIR, 'node_modules'))) {
    throw new Error(SETUP_HINT);
  }

  const assetsDir = opts.assetsDir || fs.mkdtempSync(path.join(os.tmpdir(), 'mmd-excalidraw-'));
  fs.mkdirSync(assetsDir, { recursive: true });

  // Render all diagrams in one browser launch. Any "not installed" failure
  // (missing bundle, missing Chromium) is rethrown as an actionable setup message.
  let results;
  try {
    const { renderJobs } = await import(RENDER_MJS);
    const jobs = fences.map((f, i) => ({ name: `diagram-${i + 1}`, kind: 'mermaid', input: f.def }));
    results = await renderJobs(jobs, { png: format === 'png', ...renderOpts });
  } catch (e) {
    if (isSetupError(e)) throw new Error(SETUP_HINT);
    throw e;
  }

  // Write assets + collect diagram metadata (document order).
  const diagrams = [];
  results.forEach((r, i) => {
    if (!r.ok) throw new Error(`mermaid diagram ${i + 1} failed to render: ${r.error}`);
    const file = path.join(assetsDir, `${r.name}.${format}`);
    if (format === 'png') fs.writeFileSync(file, Buffer.from(r.png, 'base64'));
    else fs.writeFileSync(file, r.svg, 'utf8');
    diagrams.push({ file, alt: `Diagram ${i + 1}`, index: fences[i].index, count: r.count });
  });

  // Splice replacements from LAST fence to FIRST so earlier offsets stay valid
  // (robust even if two diagrams share identical source).
  let out = md;
  for (let i = fences.length - 1; i >= 0; i--) {
    const f = fences[i];
    const ref = `![${diagrams[i].alt}](${diagrams[i].file})`;
    out = out.slice(0, f.index) + ref + out.slice(f.index + f.full.length);
  }

  return { md: out, diagrams, count: fences.length, assetsDir };
}

module.exports = { preprocessMermaid };
