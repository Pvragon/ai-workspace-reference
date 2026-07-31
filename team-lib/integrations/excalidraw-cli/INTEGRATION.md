---
template: integration
version: 0.3.0
summary: Generic headless Excalidraw render CLI and MCP replacement — render Excalidraw element/scene JSON (the same dialect the Excalidraw MCP's create_view takes) or Mermaid text to .excalidraw + .svg + .png + .html (responsive inline-SVG figure for pages/decks), for injecting into documents. Runs @excalidraw in headless Chromium.
created: 2026-07-13
last_updated: 2026-07-15
maintainer: your-agent
status: active
---

# excalidraw-cli (`excalidraw`)

A **generic, headless Excalidraw render CLI** — and a drop-in replacement for the
Excalidraw MCP's artifact-producing path. It takes Excalidraw element/scene JSON
(or Mermaid text) and writes `.excalidraw` + `.svg` + `.png`. No MCP process, no
server, no network at render time.

Two front-ends over one render engine:

| Command | Input | Use |
|---------|-------|-----|
| `excalidraw render`  | Excalidraw elements array / `.excalidraw` scene | **MCP `create_view` replacement** — pass the same JSON |
| `excalidraw mermaid` | Mermaid diagram text | convenience: lock the logic in Mermaid, then render |

## Why it replaces the MCP

The Excalidraw MCP's core primitive is: *element JSON → rendered image*. Its
element format (`create_view`, per the MCP `read_me`) **is** the Excalidraw
"element skeleton" dialect that `convertToExcalidrawElements` consumes. So the
exact JSON you'd hand the MCP, you can drop in a file and render — faster, no MCP
round-trips:

```bash
excalidraw render scene.json -o out/     # scene.json = the create_view array
```

Handled from the MCP dialect:
- **`label` on containers**, palette fills, bound arrows (`startBinding`/`endBinding`) — native.
- **`delete` pseudo-elements** — applied (removed ids won't render).
- **`cameraUpdate` / `restoreCheckpoint`** — stripped with a warning. Static export
  renders the whole scene (no animation, no live viewport, no checkpoint store).

What the CLI does **not** replace: the MCP's *inline animated draw-in-chat*. For
the author→see→iterate loop, `excalidraw render` + viewing the PNG covers it.

## Why a browser

`@excalidraw/mermaid-to-excalidraw` renders Mermaid through a real DOM and scrapes
geometry from the SVG — needs a browser, not pure Node. `exportToSvg`/`exportToBlob`
likewise use canvas. The engine launches one headless Chromium, injects a prebuilt
bundle (`convertToExcalidrawElements` + `exportToSvg`/`exportToBlob` +
`parseMermaidToExcalidraw`), and renders. `mmdc` is **not** a substitute for the
mermaid path — it emits mermaid-styled SVG, not the Excalidraw hand-drawn look.

## Install

```bash
cd team-lib/integrations/excalidraw-cli
npm install                      # also builds dist/bundle.js via postinstall
npx playwright install chromium  # one-time browser download (~180MB)
npm test                         # both-path smoke — expect "[smoke] OK"
```

## Usage

```bash
# GENERIC: Excalidraw element/scene JSON -> images  (MCP replacement)
excalidraw render scene.json -o out/
excalidraw render a.json b.excalidraw -o out/          # many, one browser launch
echo '[{"type":"rectangle","id":"r","x":0,"y":0,"width":200,"height":80,"label":{"text":"Hi"}}]' \
  | excalidraw render --stdin --name hi -o out/

# MERMAID: text -> images
excalidraw mermaid flow.mmd -o out/
excalidraw mermaid flow.mmd -f svg --dark --scale 3 -o out/
```

Invoked as `node bin/excalidraw.mjs <cmd> ...` until `npm link`/PATH is set up.
`render` is the default command if none is given.

### Options (both commands)

| Flag | Default | Meaning |
|------|---------|---------|
| `-o, --out-dir` | input dir / cwd | output directory |
| `-f, --formats` | `svg,png,excalidraw` | comma list |
| `--dark` | off | dark-mode export |
| `--font N` | 20 | base font size, px (mermaid only) |
| `--padding N` | 16 | export padding, px |
| `--scale N` | 2 | PNG scale factor |
| `--bg COLOR` | white / `#1e1e1e` dark | background color |
| `--no-bg` | — | transparent background |
| `--stdin` + `--name NAME` | — | read from stdin |
| `--json` | — | JSON summary of written files |

### Outputs

- `<name>.excalidraw` — editable scene, opens at excalidraw.com
- `<name>.svg` — vector; embed in branded HTML docs
- `<name>.png` — raster; Google Docs / markdown / quick review
- `<name>.html` — a responsive, centered `<figure>` + inline SVG, ready to paste
  into a hand-composed HTML presentation or self-contained page. **Opt-in via
  `-f html`.** Transparent by default (sits on the page/deck background); fixed
  width/height stripped and `viewBox` kept so it scales on mobile. Use `--dark`
  for light strokes on a dark deck. Programmatic: `svgToHtmlFigure(svg, opts)`
  from `src/html-embed.mjs`.

```bash
# Diagram for a dark glassmorphism slide (transparent, light strokes)
excalidraw mermaid flow.mmd -f html --dark -o out/   # paste out/flow.html into the slide
```

## Programmatic use (chaining from doc-gen)

```js
import { renderScene, renderMermaid, renderJobs } from ".../src/render.mjs";
const a = await renderScene(elementsArray, { png: true });   // { svg, png, excalidraw, count, warnings }
const b = await renderMermaid(mermaidText);
// renderJobs([{name, kind:"scene"|"mermaid", input}], opts) — many in one browser
```

## Notes / gotchas

- **Rebuild the bundle** after bumping `@excalidraw/*`: `npm run build`.
- Skeleton-vs-full detection: elements with a numeric `seed`/`versionNonce` are
  treated as already-full and passed straight to the exporter; everything else is
  run through `convertToExcalidrawElements`.
- Bundle is ~19MB (`dist/`, gitignored, rebuilt on install). Injected once per
  launch — not per diagram.
- Performance: one-shot launch is ~1.5–2s cold. If interactive doc-building ever
  needs sub-300ms warm renders, the next step is a persistent render daemon
  (deferred — not built).
