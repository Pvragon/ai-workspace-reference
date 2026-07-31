// Browser-side entry. esbuild bundles this into dist/bundle.js as an IIFE,
// injected into a headless Chromium page. Exposes two render primitives:
//
//   window.__renderScene(input, opts)   — GENERIC: Excalidraw elements/scene -> images
//                                          (the direct replacement for the MCP's create_view)
//   window.__renderMermaid(def, opts)   — convenience: Mermaid text -> images
//
// Both funnel into the same export path (SVG + optional PNG + .excalidraw scene).
import { parseMermaidToExcalidraw } from "@excalidraw/mermaid-to-excalidraw";
import {
  convertToExcalidrawElements,
  exportToSvg,
  exportToBlob,
} from "@excalidraw/excalidraw";

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1]);
    r.onerror = reject;
    r.readAsDataURL(blob);
  });
}

function buildAppState(opts) {
  return {
    exportBackground: opts.background !== false,
    viewBackgroundColor: opts.bgColor || (opts.dark ? "#1e1e1e" : "#ffffff"),
    exportWithDarkMode: !!opts.dark,
    exportEmbedScene: false,
  };
}

// Shared export: full ExcalidrawElement[] -> { svg, png, excalidraw }
async function exportAll(elements, files, opts) {
  const padding = opts.padding ?? 16;
  const appState = buildAppState(opts);

  const svgEl = await exportToSvg({
    elements,
    files: files || null,
    appState,
    exportPadding: padding,
  });
  const svg = new XMLSerializer().serializeToString(svgEl);

  let png = null;
  if (opts.png) {
    const scale = Number(opts.scale) || 2;
    const blob = await exportToBlob({
      elements,
      files: files || null,
      appState,
      mimeType: "image/png",
      quality: 1,
      exportPadding: padding,
      getDimensions: (w, h) => ({ width: w * scale, height: h * scale, scale }),
    });
    png = await blobToBase64(blob);
  }

  const excalidraw = {
    type: "excalidraw",
    version: 2,
    source: "excalidraw-cli",
    elements,
    appState: { viewBackgroundColor: appState.viewBackgroundColor, gridSize: null },
    files: files || {},
  };

  return { svg, png, excalidraw, count: elements.length };
}

// --- Scene preprocessing (handles the MCP element dialect) -------------------

// Apply `delete` pseudo-elements, strip camera/checkpoint pseudo-elements.
// Returns { elements, warnings } — pseudo-elements never reach the exporter.
function processPseudo(list) {
  const deleted = new Set();
  const kept = [];
  const warnings = [];
  for (const el of list) {
    if (!el || !el.type) continue;
    switch (el.type) {
      case "delete":
        String(el.ids || "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
          .forEach((id) => deleted.add(id));
        break;
      case "cameraUpdate":
        warnings.push("cameraUpdate ignored (static export renders the full scene, not a viewport)");
        break;
      case "restoreCheckpoint":
        warnings.push("restoreCheckpoint ignored (no live checkpoint store in the CLI; pass a full .excalidraw scene instead)");
        break;
      default:
        kept.push(el);
    }
  }
  return { elements: kept.filter((el) => !deleted.has(el.id)), warnings };
}

// Full Excalidraw elements carry a numeric `seed`/`versionNonce`; skeletons don't.
function looksFull(els) {
  return els.some(
    (e) => typeof e.seed === "number" || typeof e.versionNonce === "number"
  );
}

/**
 * GENERIC renderer — the MCP create_view replacement.
 * @param {Array|Object} input  an elements array, OR a scene object { elements, files, appState }
 *                              (a parsed .excalidraw file works directly)
 * @param {object} opts
 * @returns {{svg, png, excalidraw, count, warnings}}
 */
window.__renderScene = async (input, opts = {}) => {
  let raw, files = null;
  if (Array.isArray(input)) {
    raw = input;
  } else if (input && Array.isArray(input.elements)) {
    raw = input.elements;
    files = input.files || null;
  } else {
    throw new Error("scene input must be an array of elements or an object with an `elements` array");
  }

  const { elements: cleaned, warnings } = processPseudo(raw);
  if (!cleaned.length) throw new Error("scene has no drawable elements after preprocessing");

  // Skeletons (MCP dialect) need conversion; already-full scenes pass straight through.
  const elements = looksFull(cleaned) ? cleaned : convertToExcalidrawElements(cleaned);

  const out = await exportAll(elements, files, opts);
  return { ...out, warnings };
};

/**
 * Mermaid convenience path.
 */
window.__renderMermaid = async (definition, opts = {}) => {
  const fontSize = Number(opts.fontSize) || 20;
  const { elements: skeleton, files } = await parseMermaidToExcalidraw(definition, {
    themeVariables: { fontSize: `${fontSize}px` },
  });
  const elements = convertToExcalidrawElements(skeleton);
  const out = await exportAll(elements, files || null, opts);
  return { ...out, warnings: [] };
};

window.__mmdReady = true;
