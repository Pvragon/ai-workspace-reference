#!/usr/bin/env node
// excalidraw — a generic Excalidraw render CLI (headless, no MCP).
//
//   excalidraw render  <scene.json|.excalidraw ...>   Excalidraw elements/scene -> images
//   excalidraw mermaid <diagram.mmd ...>              Mermaid text -> images
//
// `render` is the direct replacement for the MCP's create_view: pass the SAME
// element JSON you'd hand the MCP (skeleton dialect with `label`, or a full
// .excalidraw scene). `delete` pseudo-elements are applied; `cameraUpdate` /
// `restoreCheckpoint` are stripped (with a warning) since static export renders
// the whole scene.
//
// Common options (both subcommands):
//   -o, --out-dir DIR     output directory (default: input dir, or cwd for stdin)
//   -f, --formats LIST    comma list of svg,png,excalidraw (default: all three)
//       --dark            dark-mode export
//       --font N          base font size px (mermaid only, default 20)
//       --padding N       export padding px (default 16)
//       --scale N         PNG scale factor (default 2)
//       --bg COLOR        background color (default #ffffff, or #1e1e1e --dark)
//       --no-bg           transparent background
//       --stdin           read from stdin (requires --name)
//       --name NAME       base filename
//       --json            print JSON summary of written files
//   -h, --help
import { renderJobs } from "../src/render.mjs";
import { svgToHtmlFigure } from "../src/html-embed.mjs";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const o = {
    inputs: [], outDir: null,
    formats: ["svg", "png", "excalidraw"],
    dark: false, font: 20, padding: 16, scale: 2, bg: null, background: true,
    stdin: false, name: null, json: false, help: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case "-o": case "--out-dir": o.outDir = next(); break;
      case "-f": case "--formats": o.formats = next().split(",").map((s) => s.trim()).filter(Boolean); break;
      case "--dark": o.dark = true; break;
      case "--font": o.font = Number(next()); break;
      case "--padding": o.padding = Number(next()); break;
      case "--scale": o.scale = Number(next()); break;
      case "--bg": o.bg = next(); o.bgSet = true; break;
      case "--no-bg": o.background = false; o.bgSet = true; break;
      case "--stdin": o.stdin = true; break;
      case "--name": o.name = next(); break;
      case "--json": o.json = true; break;
      case "-h": case "--help": o.help = true; break;
      default:
        if (a.startsWith("-")) throw new Error(`Unknown option: ${a}`);
        o.inputs.push(a);
    }
  }
  return o;
}

const HELP = `excalidraw — generic Excalidraw render CLI (headless, no MCP)

  excalidraw render  <scene.json|.excalidraw ...>   elements/scene -> images
  excalidraw mermaid <diagram.mmd ...>              Mermaid text  -> images
  excalidraw <in> --stdin --name foo                read from stdin

Options: -o/--out-dir  -f/--formats svg,png,excalidraw,html  --dark  --font N
         --padding N  --scale N  --bg COLOR  --no-bg  --name NAME  --json

Formats: svg (vector), png (raster), excalidraw (editable scene),
         html (responsive centered figure+inline SVG for pages/decks,
         transparent by default; opt-in via -f).
render = the MCP create_view replacement (accepts the same element JSON).`;

// Base filename from a path, stripping known extensions.
function baseName(f) {
  return path.basename(f).replace(/\.(mmd|mermaid|md|txt|json|excalidraw)$/i, "");
}

function buildJobs(cmd, opt) {
  const kind = cmd === "mermaid" ? "mermaid" : "scene";
  const jobs = [];
  const meta = []; // parallel {name, outDir}

  const add = (name, input, outDir) => {
    jobs.push({ name, kind, input });
    meta.push({ name, outDir });
  };

  if (opt.stdin) {
    if (!opt.name) throw new Error("--stdin requires --name");
    const text = readFileSync(0, "utf8");
    const input = kind === "mermaid" ? text : JSON.parse(text);
    add(opt.name, input, opt.outDir || process.cwd());
  }
  for (const f of opt.inputs) {
    const text = readFileSync(f, "utf8");
    const input = kind === "mermaid" ? text : JSON.parse(text);
    add(baseName(f), input, opt.outDir || path.dirname(path.resolve(f)));
  }
  return { jobs, meta };
}

async function main() {
  let argv = process.argv.slice(2);
  let cmd = "render";
  if (argv[0] === "render" || argv[0] === "mermaid") { cmd = argv[0]; argv = argv.slice(1); }
  else if (argv[0] === "help" || argv[0] === "-h" || argv[0] === "--help") { console.log(HELP); process.exit(0); }

  const opt = parseArgs(argv);
  if (opt.help || (!opt.inputs.length && !opt.stdin)) {
    console.log(HELP);
    process.exit(opt.help ? 0 : 1);
  }

  const { jobs, meta } = buildJobs(cmd, opt);
  // HTML embedding wants a transparent diagram (it sits on the page/deck bg),
  // so default `html` output to transparent unless --bg/--no-bg was explicit.
  const wantsHtml = opt.formats.includes("html");
  const background = wantsHtml && !opt.bgSet ? false : opt.background;
  const renderOpts = {
    fontSize: opt.font, padding: opt.padding, dark: opt.dark,
    bgColor: opt.bg, background, scale: opt.scale,
    png: opt.formats.includes("png"),
  };

  const results = await renderJobs(jobs, renderOpts);

  const written = [];
  let failed = 0;
  results.forEach((r, idx) => {
    const outDir = meta[idx].outDir;
    if (!r.ok) { failed++; console.error(`[FAIL] ${r.name}: ${r.error}`); return; }
    (r.warnings || []).forEach((w) => console.error(`[warn] ${r.name}: ${w}`));
    mkdirSync(outDir, { recursive: true });
    const base = path.join(outDir, r.name);
    if (opt.formats.includes("svg")) { writeFileSync(`${base}.svg`, r.svg, "utf8"); written.push(`${base}.svg`); }
    if (opt.formats.includes("png") && r.png) { writeFileSync(`${base}.png`, Buffer.from(r.png, "base64")); written.push(`${base}.png`); }
    if (opt.formats.includes("excalidraw")) { writeFileSync(`${base}.excalidraw`, JSON.stringify(r.excalidraw, null, 2), "utf8"); written.push(`${base}.excalidraw`); }
    if (opt.formats.includes("html")) { writeFileSync(`${base}.html`, svgToHtmlFigure(r.svg, { className: "excalidraw-diagram" }), "utf8"); written.push(`${base}.html`); }
    if (!opt.json) console.log(`[ok]   ${r.name} (${r.count} elements) -> ${outDir}`);
  });

  if (opt.json) console.log(JSON.stringify({ written, failed }, null, 2));
  process.exit(failed ? 2 : 0);
}

main().catch((e) => { console.error(`excalidraw error: ${e?.message || e}`); process.exit(1); });
