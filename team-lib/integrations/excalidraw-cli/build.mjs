// Bundles src/browser-entry.mjs (+ the two heavy @excalidraw packages) into a
// single dist/bundle.js IIFE that we inject into a headless Chromium page.
// Run once after install / on dependency bumps:  npm run build
import { build } from "esbuild";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

await build({
  entryPoints: [path.join(__dirname, "src", "browser-entry.mjs")],
  bundle: true,
  format: "iife",
  platform: "browser",
  target: "chrome120",
  outfile: path.join(__dirname, "dist", "bundle.js"),
  define: {
    "process.env.NODE_ENV": '"production"',
    "process.env.IS_PREACT": '"false"',
  },
  loader: {
    // Excalidraw pulls CSS + font/image assets; we only need the export geometry.
    // CSS as text = harmless unused side-effect import (no injection needed).
    ".css": "text",
    ".woff": "dataurl",
    ".woff2": "dataurl",
    ".ttf": "dataurl",
    ".otf": "dataurl",
    ".png": "dataurl",
    ".jpg": "dataurl",
    ".svg": "dataurl",
  },
  logLevel: "info",
});

console.log("[excalidraw-cli] built dist/bundle.js");
