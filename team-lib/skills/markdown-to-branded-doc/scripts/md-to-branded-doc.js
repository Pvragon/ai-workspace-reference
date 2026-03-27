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
 *   node md-to-branded-doc.js doc.md plan.json --brand acme-corp --type doc-legal --format gdoc
 *   node md-to-branded-doc.js doc.md doc.docx  # defaults: pvragon, doc-report, docx
 */

const fs = require('fs');
const { loadBrandedTemplate, listAvailableBrands, listAvailableTypes, DEFAULT_BRAND, DEFAULT_TYPE } = require('./lib/brand-loader');
const { parseMarkdown } = require('./lib/parser');
const { renderDocx } = require('./render-branded-docx');
const { renderGdoc } = require('./render-branded-gdoc');
const { renderGslides } = require('./render-branded-gslides');

function main() {
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

    for (let i = 2; i < args.length; i++) {
        if (args[i] === '--brand' && args[i + 1]) {
            brandName = args[++i];
        } else if (args[i] === '--type' && args[i + 1]) {
            docType = args[++i];
        } else if (args[i] === '--format' && args[i + 1]) {
            format = args[++i].toLowerCase();
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

    // Parse markdown to IR
    const mdContent = fs.readFileSync(inputPath, 'utf8');
    const ir = parseMarkdown(mdContent);

    const brandLabel = template.composedFrom?.brand || brandName;
    console.log(`Input: ${inputPath}`);
    console.log(`Format: ${format}`);
    console.log(`Brand: ${brandLabel}`);
    console.log(`Type: ${docType}`);
    console.log(`Blocks: ${ir.blocks.length}`);
    console.log('');

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
    console.log('  node md-to-branded-doc.js doc.md doc.docx --brand acme-corp --type doc-legal');
    console.log('  node md-to-branded-doc.js doc.md plan.json --brand pvragon --type doc-report --format gdoc');
}

main();
