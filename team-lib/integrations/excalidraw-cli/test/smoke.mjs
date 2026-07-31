// Smoke test: exercise BOTH front-ends in one run.
//   1. mermaid text -> images
//   2. generic scene (MCP-dialect skeleton, incl. a `delete` pseudo-element) -> images
import { renderMermaid, renderScene } from "../src/render.mjs";
import assert from "node:assert";

// --- 1. Mermaid path ---
const MMD = `flowchart LR
  A[Start] --> B{Decision}
  B -->|yes| C[Do thing]
  B -->|no| D[Skip]
  C --> E[End]
  D --> E`;
const m = await renderMermaid(MMD, { png: true });
assert(m.svg.includes("<svg"), "mermaid svg wrong");
assert(m.png && m.png.length > 500, "mermaid png missing");
assert(m.excalidraw.elements.length > 0, "mermaid: no elements");

// --- 2. Generic scene path (same JSON shape the MCP create_view takes) ---
const SCENE = [
  { type: "cameraUpdate", width: 800, height: 600, x: 0, y: 0 }, // should be stripped
  { type: "rectangle", id: "b1", x: 100, y: 100, width: 200, height: 100, roundness: { type: 3 }, backgroundColor: "#a5d8ff", fillStyle: "solid", label: { text: "Start", fontSize: 20 } },
  { type: "rectangle", id: "b2", x: 450, y: 100, width: 200, height: 100, roundness: { type: 3 }, backgroundColor: "#b2f2bb", fillStyle: "solid", label: { text: "End", fontSize: 20 } },
  { type: "rectangle", id: "b3", x: 450, y: 260, width: 200, height: 80, backgroundColor: "#ffc9c9", fillStyle: "solid", label: { text: "removed", fontSize: 16 } },
  { type: "arrow", id: "a1", x: 300, y: 150, width: 150, height: 0, points: [[0, 0], [150, 0]], endArrowhead: "arrow", startBinding: { elementId: "b1", fixedPoint: [1, 0.5] }, endBinding: { elementId: "b2", fixedPoint: [0, 0.5] } },
  { type: "delete", ids: "b3" }, // b3 must not appear
];
const s = await renderScene(SCENE, { png: true });
assert(s.svg.includes("<svg"), "scene svg wrong");
assert(s.png && s.png.length > 500, "scene png missing");
assert(s.warnings.some((w) => w.includes("cameraUpdate")), "expected cameraUpdate warning");
assert(!JSON.stringify(s.excalidraw.elements).includes("removed"), "delete pseudo-element not applied");

console.log(
  `[smoke] OK — mermaid ${m.excalidraw.elements.length} els / ${m.svg.length}b svg; ` +
    `scene ${s.count} els / ${s.svg.length}b svg; warnings=${s.warnings.length}`
);
