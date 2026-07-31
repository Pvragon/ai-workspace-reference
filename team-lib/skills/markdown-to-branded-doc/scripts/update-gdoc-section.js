#!/usr/bin/env node

/**
 * Google Docs Surgical Section Updater
 * @version 1.0.0
 * @date 2026-04-21
 *
 * Replaces a single section of an existing branded Google Doc with freshly-rendered
 * content from an updated source markdown file — without touching the rest of the doc.
 *
 * This is the surgical alternative to clearing the whole body and re-rendering:
 * only the target section is modified. Page numbers, headers, brand styling, and
 * all other sections remain exactly as they were.
 *
 * A "section" is defined as a heading (H2 or H3 in the rendered doc) plus all
 * content up to (but not including) the next same-or-higher-level heading.
 *
 * Usage:
 *   node update-gdoc-section.js <source.md> <doc-id> --section "<heading-text>" [options]
 *
 * Options:
 *   --section "<text>"   Heading text of the section to replace (exact match, case-sensitive).
 *                        The section extends until the next same-or-higher-level heading or EOF.
 *   --brand <name>       Brand slug (default: pvragon)
 *   --type <type>        Document type (default: doc-report)
 *   --dry-run            Show what would change without modifying the doc
 *
 * Notes / Limitations:
 *   - Source and existing doc must use the same heading text for the section.
 *   - Section cannot contain tables (warning will be issued; fall back to full re-render).
 *   - Orphan detection is NOT re-run; pagination of other sections is unchanged.
 *   - Header/footer and page numbers are never touched.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');
const { loadBrandedTemplate, DEFAULT_BRAND, DEFAULT_TYPE } = require('./lib/brand-loader');
const { parseMarkdown } = require('./lib/parser');
const { renderGdoc } = require('./render-branded-gdoc');

// ============================================================================
// MAIN
// ============================================================================

function main() {
    const args = process.argv.slice(2);

    if (args.length < 2) {
        printUsage();
        process.exit(1);
    }

    const sourcePath = args[0];
    const docId = args[1];

    let sectionHeading = null;
    let brandName = DEFAULT_BRAND;
    let docType = DEFAULT_TYPE;
    let dryRun = false;

    for (let i = 2; i < args.length; i++) {
        if (args[i] === '--section' && args[i + 1]) {
            sectionHeading = args[++i];
        } else if (args[i] === '--brand' && args[i + 1]) {
            brandName = args[++i];
        } else if (args[i] === '--type' && args[i + 1]) {
            docType = args[++i];
        } else if (args[i] === '--dry-run') {
            dryRun = true;
        }
    }

    if (!sectionHeading) {
        console.error('ERROR: --section "<heading-text>" is required');
        printUsage();
        process.exit(1);
    }

    if (!fs.existsSync(sourcePath)) {
        console.error(`Source markdown not found: ${sourcePath}`);
        process.exit(1);
    }

    console.log(`Source: ${sourcePath}`);
    console.log(`Doc ID: ${docId}`);
    console.log(`Section: "${sectionHeading}"`);
    console.log(`Brand: ${brandName} / Type: ${docType}`);
    console.log(`Mode: ${dryRun ? 'DRY RUN' : 'LIVE'}`);
    console.log('');

    // ---------- Step 1: Extract the target section from source markdown ----------
    const mdContent = fs.readFileSync(sourcePath, 'utf8');
    const extracted = extractSectionFromMarkdown(mdContent, sectionHeading);
    if (!extracted) {
        console.error(`ERROR: Section heading "${sectionHeading}" not found in ${sourcePath}`);
        process.exit(1);
    }
    console.log(`Extracted section from source (depth=${extracted.depth}, ${extracted.markdown.split('\n').length} lines)`);

    // Build a set of heading texts at equal-or-higher level from the source markdown.
    // We use this to disambiguate "real" headings from body paragraphs that may have
    // been mis-styled in the existing doc (e.g., by a prior broken surgical run).
    const validBoundaryHeadings = collectHeadingsAtOrAbove(mdContent, extracted.depth);
    validBoundaryHeadings.delete(sectionHeading.trim());
    console.log(`Will terminate range at next heading in: ${validBoundaryHeadings.size} known boundary candidates`);

    // Early warning: tables inside the section mean index alignment will be harder.
    // MVP doesn't support tables in surgical updates — user must use full re-render.
    if (/^\s*\|.*\|/m.test(extracted.markdown)) {
        console.warn('WARNING: The section appears to contain a table. Tables are not yet supported in surgical updates.');
        console.warn('         Either remove the table, or fall back to full-body re-render.');
        process.exit(2);
    }

    // ---------- Step 2: Render the section alone → mini render plan ----------
    const template = loadBrandedTemplate(brandName, docType);
    const ir = parseMarkdown(extracted.markdown);
    const tempPlanPath = path.join(os.tmpdir(), `section-plan-${Date.now()}.json`);
    renderGdoc(ir, template, tempPlanPath);
    const miniPlan = JSON.parse(fs.readFileSync(tempPlanPath, 'utf8'));
    try { fs.unlinkSync(tempPlanPath); } catch (_) {}
    console.log(`Rendered section → ${miniPlan.content.length} chars, ${miniPlan.requests.length} formatting requests, ${miniPlan.listItems.length} list items`);

    // ---------- Step 3: Fetch the existing doc structure ----------
    const existingDoc = gws('docs', 'documents', 'get', { documentId: docId });

    // ---------- Step 4: Find the section's range in the existing doc ----------
    const existingRange = findSectionRangeInDoc(existingDoc, sectionHeading, extracted.depth, validBoundaryHeadings);
    if (!existingRange) {
        console.error(`ERROR: Section heading "${sectionHeading}" not found in doc ${docId}`);
        console.error('       Make sure the heading text matches exactly (case-sensitive).');
        process.exit(1);
    }
    console.log(`Found section in doc: startIndex=${existingRange.startIndex}, endIndex=${existingRange.endIndex} (${existingRange.endIndex - existingRange.startIndex} chars to replace)`);

    if (dryRun) {
        console.log('\n[DRY RUN] Would execute:');
        console.log(`  1. deleteContentRange [${existingRange.startIndex}, ${existingRange.endIndex})`);
        console.log(`  2. insertText at ${existingRange.startIndex} (${miniPlan.content.length} chars)`);
        console.log(`  3. Apply ${miniPlan.requests.length} formatting requests (offset by ${existingRange.startIndex - 1})`);
        console.log(`  4. Apply ${miniPlan.listItems.length} native bullet ranges (offset by ${existingRange.startIndex - 1})`);
        return;
    }

    // ---------- Step 5: Apply the edits ----------

    // 5a: Delete old section + insert new content in ONE batchUpdate.
    // Doing these together keeps the doc consistent and simplifies index arithmetic.
    const deleteAndInsert = [
        {
            deleteContentRange: {
                range: { startIndex: existingRange.startIndex, endIndex: existingRange.endIndex }
            }
        },
        {
            insertText: {
                location: { index: existingRange.startIndex },
                text: miniPlan.content
            }
        }
    ];
    gws('docs', 'documents', 'batchUpdate', { documentId: docId }, { requests: deleteAndInsert });
    console.log('Deleted old section and inserted new content');

    // 5b: RESET the inserted range to NORMAL_TEXT paragraph style before applying
    // the mini-plan's formatting. Without this, inserted paragraphs inherit the
    // namedStyleType of the text at the insertion point (typically HEADING_2 from
    // the old section's heading), which leaks the heading style across body
    // paragraphs of the new content.
    const insertedStart = existingRange.startIndex;
    const insertedEnd = existingRange.startIndex + miniPlan.content.length;
    gws('docs', 'documents', 'batchUpdate', { documentId: docId }, {
        requests: [{
            updateParagraphStyle: {
                range: { startIndex: insertedStart, endIndex: insertedEnd },
                paragraphStyle: { namedStyleType: 'NORMAL_TEXT' },
                fields: 'namedStyleType'
            }
        }]
    });
    console.log('Reset inserted range to NORMAL_TEXT baseline');

    // 5c: Apply formatting requests with index offset.
    // Mini plan indices are 1-based (fresh doc). We need them to be relative to
    // the insertion point: newIndex = (miniIndex - 1) + existingRange.startIndex
    const offset = existingRange.startIndex - 1;
    const shiftedRequests = shiftRequestIndices(miniPlan.requests, offset);

    // Batch formatting into a single batchUpdate (same as full-body path does).
    if (shiftedRequests.length > 0) {
        // Split into chunks of 500 to stay under API limits for very large sections
        const chunkSize = 500;
        for (let i = 0; i < shiftedRequests.length; i += chunkSize) {
            const chunk = shiftedRequests.slice(i, i + chunkSize);
            gws('docs', 'documents', 'batchUpdate', { documentId: docId }, { requests: chunk });
        }
        console.log(`Applied ${shiftedRequests.length} formatting requests`);
    }

    // 5d: Apply native bullets with offset
    if (miniPlan.listItems && miniPlan.listItems.length > 0) {
        const bulletRequests = miniPlan.listItems.map(item => ({
            createParagraphBullets: {
                range: {
                    startIndex: item.startIndex + offset,
                    endIndex: item.endIndex + offset
                },
                bulletPreset: item.ordered ? 'NUMBERED_DECIMAL_ALPHA_ROMAN' : 'BULLET_DISC_CIRCLE_SQUARE'
            }
        }));
        gws('docs', 'documents', 'batchUpdate', { documentId: docId }, { requests: bulletRequests });
        console.log(`Applied ${miniPlan.listItems.length} native bullet ranges`);
    }

    console.log('\nDone. Doc URL:');
    console.log(`https://docs.google.com/document/d/${docId}/edit`);
}

// ============================================================================
// MARKDOWN SECTION EXTRACTION
// ============================================================================

/**
 * Extract a section from markdown: the heading matching sectionText, plus all
 * content up to (but not including) the next heading at the same or higher level.
 *
 * Returns { markdown, depth } or null if not found.
 */
function extractSectionFromMarkdown(mdContent, sectionText) {
    // Strip frontmatter if present
    let body = mdContent;
    const frontmatterMatch = body.match(/^---\n[\s\S]*?\n---\n/);
    if (frontmatterMatch) {
        body = body.slice(frontmatterMatch[0].length);
    }

    const lines = body.split('\n');
    const targetText = sectionText.trim();

    // Find the heading line
    let headingLineIdx = -1;
    let headingDepth = -1;
    for (let i = 0; i < lines.length; i++) {
        const m = lines[i].match(/^(#+)\s+(.+?)\s*$/);
        if (m && m[2].trim() === targetText) {
            headingLineIdx = i;
            headingDepth = m[1].length;
            break;
        }
    }

    if (headingLineIdx === -1) return null;

    // Find the end of the section: next heading at same or higher level (depth <= headingDepth)
    let endLineIdx = lines.length;
    for (let i = headingLineIdx + 1; i < lines.length; i++) {
        const m = lines[i].match(/^(#+)\s+(.+?)\s*$/);
        if (m && m[1].length <= headingDepth) {
            endLineIdx = i;
            break;
        }
    }

    const sectionLines = lines.slice(headingLineIdx, endLineIdx);
    // Trim trailing blank lines
    while (sectionLines.length > 0 && sectionLines[sectionLines.length - 1].trim() === '') {
        sectionLines.pop();
    }

    return {
        markdown: sectionLines.join('\n') + '\n',
        depth: headingDepth
    };
}

// ============================================================================
// EXISTING DOC SECTION RANGE LOOKUP
// ============================================================================

/**
 * Walk an existing Google Doc's structuralElements to find the range occupied
 * by a given section (heading text + following content up to next same-or-higher heading).
 *
 * sourceDepth is the markdown heading depth (e.g., 3 for "###"). The renderer maps:
 *   depth=1 (title) → NAMED_STYLE_TYPE = TITLE
 *   depth=2         → HEADING_1
 *   depth=3         → HEADING_2
 *   depth=4+        → HEADING_3
 *
 * We match by normalized text and find the next structural element whose
 * namedStyleType corresponds to an equal-or-higher-level heading.
 *
 * Returns { startIndex, endIndex } or null.
 */
function findSectionRangeInDoc(doc, sectionText, sourceDepth, validBoundaryHeadings) {
    const body = doc.body;
    if (!body || !body.content) return null;

    const target = sectionText.trim();
    const targetStyle = markdownDepthToNamedStyle(sourceDepth);
    const higherStyles = namedStylesAtOrAbove(targetStyle);

    let startIndex = null;
    let endIndex = null;

    for (const el of body.content) {
        if (!el.paragraph) continue;
        const style = el.paragraph.paragraphStyle?.namedStyleType;
        const text = paragraphPlainText(el.paragraph).trim();

        if (startIndex === null) {
            // Looking for the start of the target section.
            // Match by exact text AND heading style.
            if (style === targetStyle && text === target) {
                startIndex = el.startIndex;
            }
        } else {
            // We're past the heading; look for the next same-or-higher-level heading.
            // Use two signals together (AND): heading style AND text matching a known
            // boundary heading from the source markdown. This disambiguates real
            // headings from body paragraphs that may have inherited heading style
            // from a prior broken run.
            const looksHeadingStyled = style && higherStyles.has(style);
            const isKnownBoundary = validBoundaryHeadings && validBoundaryHeadings.has(text);
            if (looksHeadingStyled && isKnownBoundary) {
                endIndex = el.startIndex;
                break;
            }
        }
    }

    if (startIndex === null) return null;

    // If we never found a terminating heading, the section runs to doc end.
    // Use the endIndex of the last content element (minus 1 to preserve final newline).
    if (endIndex === null) {
        const last = body.content[body.content.length - 1];
        endIndex = last.endIndex - 1;
    }

    return { startIndex, endIndex };
}

/**
 * Collect the text of all headings at or above a given depth from a markdown string.
 * Used to build the allowed set of section-boundary heading texts.
 */
function collectHeadingsAtOrAbove(mdContent, maxDepth) {
    let body = mdContent;
    const frontmatterMatch = body.match(/^---\n[\s\S]*?\n---\n/);
    if (frontmatterMatch) body = body.slice(frontmatterMatch[0].length);

    const set = new Set();
    for (const line of body.split('\n')) {
        const m = line.match(/^(#+)\s+(.+?)\s*$/);
        if (m && m[1].length <= maxDepth) {
            set.add(m[2].trim());
        }
    }
    return set;
}

function markdownDepthToNamedStyle(depth) {
    // Markdown depth → named style, matching parser.js logic for depth > 1
    if (depth <= 1) return 'TITLE';
    if (depth === 2) return 'HEADING_1';
    if (depth === 3) return 'HEADING_2';
    return 'HEADING_3';
}

function namedStylesAtOrAbove(style) {
    // Returns the set of named styles that are "equal or higher level" than the given one.
    // Higher = more structurally significant = smaller number in HEADING_N.
    const order = ['TITLE', 'HEADING_1', 'HEADING_2', 'HEADING_3', 'HEADING_4', 'HEADING_5', 'HEADING_6'];
    const idx = order.indexOf(style);
    if (idx === -1) return new Set([style]);
    return new Set(order.slice(0, idx + 1));
}

function paragraphPlainText(paragraph) {
    if (!paragraph.elements) return '';
    return paragraph.elements
        .map(e => e.textRun?.content || '')
        .join('')
        .replace(/\n+$/, '');
}

// ============================================================================
// INDEX OFFSET HELPERS
// ============================================================================

/**
 * Shift all startIndex/endIndex/index fields in a batch of requests by the given offset.
 * Recursively walks nested structures.
 */
function shiftRequestIndices(requests, offset) {
    if (offset === 0) return requests;
    return requests.map(req => shiftObjectIndices(req, offset));
}

function shiftObjectIndices(obj, offset) {
    if (Array.isArray(obj)) {
        return obj.map(item => shiftObjectIndices(item, offset));
    }
    if (obj && typeof obj === 'object') {
        const out = {};
        for (const [k, v] of Object.entries(obj)) {
            if ((k === 'startIndex' || k === 'endIndex' || k === 'index') && typeof v === 'number') {
                out[k] = v + offset;
            } else {
                out[k] = shiftObjectIndices(v, offset);
            }
        }
        return out;
    }
    return obj;
}

// ============================================================================
// gws CLI HELPERS
// ============================================================================

function gws(service, resource, method, params, body) {
    let cmd = `gws ${service} ${resource} ${method}`;
    if (params) {
        cmd += ` --params '${JSON.stringify(params)}'`;
    }
    if (body) {
        // Use a temp file for the body to avoid shell quoting issues
        const bodyPath = path.join(os.tmpdir(), `gws-body-${Date.now()}-${Math.random().toString(36).slice(2)}.json`);
        fs.writeFileSync(bodyPath, JSON.stringify(body));
        cmd += ` --json "$(cat ${bodyPath})"`;
        try {
            const stdout = execSync(cmd, { encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 });
            return parseGwsOutput(stdout);
        } finally {
            try { fs.unlinkSync(bodyPath); } catch (_) {}
        }
    } else {
        const stdout = execSync(cmd, { encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 });
        return parseGwsOutput(stdout);
    }
}

function parseGwsOutput(stdout) {
    // gws prepends "Using keyring backend: keyring" on first line
    const trimmed = stdout.replace(/^Using keyring backend:.*\n?/gm, '').trim();
    if (!trimmed) return null;
    try { return JSON.parse(trimmed); } catch (_) { return trimmed; }
}

// ============================================================================
// USAGE
// ============================================================================

function printUsage() {
    console.log('Usage:');
    console.log('  node update-gdoc-section.js <source.md> <doc-id> --section "<heading>" [options]');
    console.log('');
    console.log('Required:');
    console.log('  <source.md>          Path to updated source markdown file');
    console.log('  <doc-id>             Existing Google Doc ID');
    console.log('  --section "<text>"   Exact heading text of the section to replace');
    console.log('');
    console.log('Options:');
    console.log('  --brand <name>       Brand slug (default: pvragon)');
    console.log('  --type <type>        Document type (default: doc-report)');
    console.log('  --dry-run            Show what would change without modifying the doc');
}

main();
