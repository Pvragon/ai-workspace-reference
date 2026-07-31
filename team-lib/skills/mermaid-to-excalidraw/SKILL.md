---
template: skill-definition
version: 1.1.0
summary: "Render a COMPLETED (logic-locked) Mermaid diagram into a good-looking Excalidraw image (.svg/.png/.excalidraw/.html) for a document, deck, or page, with a mandatory visual-verify loop. Wraps the excalidraw-cli. Not for iterating diagram logic — that stays in Mermaid."
created: 2026-07-14
last_updated: 2026-07-15
maintainer: pvragon
---

# Skill: Mermaid → Excalidraw

## When to Use

Use this **after** a Mermaid diagram's logic is locked, to produce the final
hand-drawn Excalidraw artifact for a document. The split is deliberate:

- **Mermaid** = iterate the *logic* (nodes, edges, labels, branching). Fast,
  text-based, diffable. Do all structural iteration here first.
- **This skill** = one-way final render of that locked Mermaid into Excalidraw
  images, plus a visual check that it actually looks right.

Do **not** use this to iterate logic (re-render churn), and do **not** use it for
design work — that's pencil.dev. `mmdc` is not a substitute; it produces
mermaid-styled output, not the Excalidraw hand-drawn look.

Prereq: the `excalidraw` CLI (`team-lib/integrations/excalidraw-cli/`). If it's
never been set up: `cd` there, `npm install`, `npx playwright install chromium`,
`npm test` (expect `[smoke] OK`).

## Hard guardrails (read first)

1. **Logic must be locked.** If you're still changing what the diagram *says*,
   go back to Mermaid. This skill is a render step, not an editor.
2. **Visual verification is MANDATORY, not optional.** A clean CLI exit means the
   file was written — NOT that it looks right. You MUST `Read` the PNG and inspect
   it before treating the artifact as done (see step 4). `status=ok` ≠ good-looking.
3. **The `.mmd` source is the source of truth.** Keep it next to the outputs so the
   diagram can be re-rendered/edited later. Never hand-edit the generated
   `.svg`/`.excalidraw` for content changes — edit the Mermaid and re-render.

## Procedure

### 1. Capture the locked Mermaid source
Write the finalized Mermaid to a `.mmd` file (don't pipe ephemeral text you can't
re-render). Name it for the diagram, e.g. `billing-flow.mmd`. For a doc-bound
diagram, put it alongside where the outputs will live.

### 2. Pick output formats + options
Defaults render svg + png + excalidraw. Choose deliberately:
- **`.svg`** — for branded HTML docs / anything vector (scales crisply). Usually the one you inject.
- **`.png`** — for Google Docs, markdown, and the visual-verify step. `--scale 3` for high-DPI.
- **`.excalidraw`** — the editable scene; keep it if someone may tweak by hand at excalidraw.com.
- **`.html`** (opt-in `-f html`) — a responsive, centered, transparent `<figure>` + inline SVG
  to paste into a hand-composed **HTML presentation or self-contained page**. Pair with
  `--dark` for light strokes on a dark deck. (The `markdown-to-branded-doc` HTML pathway uses this.)
- **`--dark`** — for dark-themed docs/decks (light strokes).
- **`--font N`** / **`--padding N`** — bump if labels look cramped or clipped in step 4.

### 3. Render
```bash
node team-lib/integrations/excalidraw-cli/bin/excalidraw.mjs mermaid \
  <path>/<name>.mmd -o <out-dir>/ [-f svg,png,excalidraw] [--dark] [--scale 3]
```
If it `[FAIL]`s with a Mermaid parse error, the **Mermaid syntax** is wrong — fix
the `.mmd` and re-render. (A render failure here is almost always a diagram-logic
problem that slipped through, not a tool problem.)

### 4. Visually verify (MANDATORY)
`Read` the generated `.png` and inspect it as an image. Check:
- **Labels** — all present, legible, not clipped or overflowing their shapes.
- **Edges/arrows** — connect the correct nodes; arrowheads point the right way.
- **Layout** — no overlapping shapes/labels; nothing runs off the canvas.
- **Text** — branch labels (`yes`/`no`, etc.) readable and on the right edges.

If anything's off:
- Label cramped/clipped → `--font` down a touch, or `--padding` up, and re-render.
- Layout tangled → the fix is usually in the **Mermaid** (direction `TD`/`LR`,
  node ordering, subgraphs). Adjust the `.mmd`, re-render, re-verify.
Loop until the PNG looks right. This is the whole point of the skill.

### 5. Place + inject
- Keep `.mmd` + outputs together. For a deliverable, follow workspace naming
  (`YYMMDD-name.*`) and location rules (`runtime/deliverables/` for finals).
- Inject the `.svg` (HTML docs) or `.png` (Google Docs / markdown) into the target
  document, referencing the artifact you just verified.

## Programmatic alternative (for scripts / doc-gen)
When rendering from a script rather than by hand, import the engine directly —
no subprocess:
```js
import { renderMermaid } from "team-lib/integrations/excalidraw-cli/src/render.mjs";
const { svg, png, excalidraw } = await renderMermaid(mermaidText, { png: true });
```
This is the hook the doc-gen wiring uses (Mermaid fences → Excalidraw SVG,
default-on but skippable).

## Notes
- One-shot render is ~1.5–2s (cold Chromium launch). Rendering several diagrams?
  Pass them all in one `excalidraw mermaid a.mmd b.mmd c.mmd` — one browser launch,
  amortized. Or use `renderJobs([...])` programmatically.
- The generic `excalidraw render <scene.json>` path (arbitrary Excalidraw element
  JSON, the MCP `create_view` replacement) is a CLI feature, out of scope for this
  skill — see `excalidraw-cli/INTEGRATION.md`.
