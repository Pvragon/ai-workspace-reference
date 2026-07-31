#!/usr/bin/env node

/**
 * Markdown to Branded Document Converter (Unified CLI)
 * @version 1.0.0
 * @date 2026-03-19
 *
 * Converts markdown files to branded documents in multiple formats:
 *   - docx: Generates a .docx file directly (requires docx, image-size)
 *   - gdoc: Generates a JSON render plan for Google Docs (executed via gws CLI)
 *
 * Usage:
 *   node md-to-branded-doc.js <input.md> <output> [--brand <brand>] [--type <type>] [--format docx|gdoc]
 *
 * Examples:
 *   node md-to-branded-doc.js doc.md doc.docx --brand pvragon --type doc-report --format docx
 *   node md-to-branded-doc.js doc.md plan.json --brand acme-health --type doc-legal --format gdoc
 *   node md-to-branded-doc.js doc.md doc.docx  # defaults: pvragon, doc-report, docx
 */

const fs = require('fs');
const path = require('path');
const { loadBrandedTemplate, listAvailableBrands, listAvailableTypes, DEFAULT_BRAND, DEFAULT_TYPE } = require('./lib/brand-loader');
const { parseMarkdown } = require('./lib/parser');
const { preprocessMermaid } = require('./lib/mermaid-preprocess');
const { renderDocx } = require('./render-branded-docx');
const { renderGdoc } = require('./render-branded-gdoc');
const { renderGslides } = require('./render-branded-gslides');

async function main() {
    const args = process.argv.slice(2);

    if (args.length < 2) {
        printUsage();
        process.exit(1);
    }

    const inputPath = args[0];
    const outputPath = args[1];

    // Parse named arguments
    let brandName = DEFAULT_BRAND;
    let docType = DEFAULT_TYPE;
    let format = 'docx';
    let renderMetadataTable = false;
    let mermaidExcalidraw = true;   // default-on: ```mermaid fences -> Excalidraw images
    let mermaidFormat = null;       // override; else per-target default

    for (let i = 2; i < args.length; i++) {
        if (args[i] === '--brand' && args[i + 1]) {
            brandName = args[++i];
        } else if (args[i] === '--type' && args[i + 1]) {
            docType = args[++i];
        } else if (args[i] === '--format' && args[i + 1]) {
            format = args[++i].toLowerCase();
        } else if (args[i] === '--render-metadata-table') {
            renderMetadataTable = true;
        } else if (args[i] === '--no-excalidraw' || args[i] === '--no-mermaid-render') {
            mermaidExcalidraw = false;   // opt out: leave mermaid fences as raw text
        } else if (args[i] === '--mermaid-format' && args[i + 1]) {
            mermaidFormat = args[++i].toLowerCase();
        } else if (args[i] === '--list-brands') {
            console.log('Available brands:', listAvailableBrands().join(', '));
            process.exit(0);
        } else if (args[i] === '--list-types') {
            const brand = args[i + 1] || brandName;
            console.log(`Available types for ${brand}:`, listAvailableTypes(brand).join(', '));
            process.exit(0);
        }
    }

    // Validate input file
    if (!fs.existsSync(inputPath)) {
        console.error(`Input file not found: ${inputPath}`);
        process.exit(1);
    }

    if (!['docx', 'gdoc', 'gslides'].includes(format)) {
        console.error(`Unknown format: ${format}. Use "docx", "gdoc", or "gslides".`);
        process.exit(1);
    }

    // Load pre-composed branded template
    const template = loadBrandedTemplate(brandName, docType);

    // Read markdown, then convert any ```mermaid fences to Excalidraw images
    // (default-on; --no-excalidraw opts out). raster (png) embeds in every
    // target; svg is offered for vector targets that support it.
    let mdContent = fs.readFileSync(inputPath, 'utf8');
    const diagramFormat = mermaidFormat || 'png';
    // Stable assets dir next to the output — the gdoc flow executes the plan in a
    // SEPARATE later process, so diagram files must persist (a temp dir would not).
    const outBase = path.basename(outputPath).replace(/\.[^.]+$/, '');
    const assetsDir = path.join(path.dirname(path.resolve(outputPath)), `${outBase}-diagrams`);
    const pre = await preprocessMermaid(mdContent, {
        enabled: mermaidExcalidraw,
        format: diagramFormat,
        assetsDir,
    });
    mdContent = pre.md;
    if (pre.count) {
        console.log(pre.skipped
            ? `Mermaid: ${pre.count} fence(s) left raw (--no-excalidraw)`
            : `Mermaid: rendered ${pre.count} diagram(s) -> Excalidraw ${diagramFormat}`);
    }

    // Parse markdown to IR
    const ir = parseMarkdown(mdContent, { renderMetadataTable });

    const brandLabel = template.composedFrom?.brand || brandName;
    console.log(`Input: ${inputPath}`);
    console.log(`Format: ${format}`);
    console.log(`Brand: ${brandLabel}`);
    console.log(`Type: ${docType}`);
    console.log(`Blocks: ${ir.blocks.length}`);
    console.log('');

    // Body-image embedding is implemented for docx and gdoc. gslides is not yet
    // wired — surface it loudly rather than silently dropping diagrams.
    if (pre.count && !pre.skipped && format === 'gslides') {
        console.warn(`  ⚠ ${pre.count} Excalidraw diagram(s) rendered to ${pre.assetsDir}, but the`);
        console.warn(`    gslides renderer does not embed body images yet — they will NOT appear in the output.`);
        console.warn(`    (docx + gdoc embed them today; gslides body-image support is a follow-up.)`);
    }

    // Dispatch to renderer
    if (format === 'docx') {
        renderDocx(ir, template, outputPath);
    } else if (format === 'gdoc') {
        renderGdoc(ir, template, outputPath);
    } else if (format === 'gslides') {
        renderGslides(ir, template, outputPath);
    }
}

function printUsage() {
    console.log('Usage: node md-to-branded-doc.js <input.md> <output> [--brand <brand>] [--type <type>] [--format docx|gdoc]');
    console.log('');
    console.log('Formats:');
    console.log('  docx   Generate a .docx file (default)');
    console.log('  gdoc   Generate a JSON render plan for Google Docs');
    console.log('');
    console.log('Options:');
    console.log('  --brand       Brand/company slug (default: pvragon)');
    console.log('  --type        Document type (default: doc-report)');
    console.log('  --format      Output format: docx or gdoc (default: docx)');
    console.log('  --list-brands List available brands');
    console.log('  --list-types  List available document types for a brand');
    console.log('');
    console.log('Document types:');
    console.log('  doc-report             Standard report');
    console.log('  doc-report-cover       Report with cover page');
    console.log('  doc-letterhead         Company letterhead');
    console.log('  doc-legal              Legal document');
    console.log('  slides-informational   Content-dense slides');
    console.log('  slides-formal          Presentation slides');
    console.log('  html-presentation      Standalone HTML presentation');
    console.log('');
    console.log('Examples:');
    console.log('  node md-to-branded-doc.js doc.md doc.docx');
    console.log('  node md-to-branded-doc.js doc.md doc.docx --brand acme-health --type doc-legal');
    console.log('  node md-to-branded-doc.js doc.md plan.json --brand pvragon --type doc-report --format gdoc');
}

main().catch(err => {
    console.error(`Error: ${err.message}`);
    process.exit(1);
});
