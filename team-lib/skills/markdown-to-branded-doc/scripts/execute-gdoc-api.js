#!/usr/bin/env node

/**
 * Google Docs Plan Executor (gws CLI)
 * @version 1.0.0
 * @date 2026-03-19
 *
 * Reads a render plan produced by render-branded-gdoc.js and executes it via the
 * gws CLI (Google Workspace CLI). This replaces the previous workflow where
 * the agent manually executed each operation via MCP tools.
 *
 * Usage:
 *   node execute-gdoc-api.js <plan.json> [--folder <folderId>] [--dry-run]
 *
 * Steps:
 *   1. Create the Google Doc (from page-number template when enabled)
 *   2. Insert all text content via batchUpdate
 *   3. Apply native bullets
 *   4. Apply all formatting via batchUpdate (single API call!)
 *   5. Insert tables, optimize column widths, apply dense formatting
 *   6. Insert keyword page breaks (appendix, exhibit, schedule, signature)
 *   7. Set header (favicon pages 2+) and first-page logo (body top)
 *   8. PDF-based orphan heading detection (iterative, top-down)
 *   9. Move to Drive folder (if specified)
 */

const { execSync } = require('child_process');
const fs = require('fs');
const orphanDetection = require('./lib/orphan-detection');

// ============================================================================
// MAIN
// ============================================================================

function main() {
    const args = process.argv.slice(2);

    if (args.length < 1) {
        console.log('Usage: node execute-gdoc-api.js <plan.json> [--folder <folderId>] [--dry-run]');
        process.exit(1);
    }

    const planPath = args[0];
    let folderId = null;
    let dryRun = false;

    for (let i = 1; i < args.length; i++) {
        if (args[i] === '--folder' && args[i + 1]) {
            folderId = args[++i];
        } else if (args[i] === '--dry-run') {
            dryRun = true;
        }
    }

    if (!fs.existsSync(planPath)) {
        console.error(`Plan file not found: ${planPath}`);
        process.exit(1);
    }

    const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
    console.log(`Executing render plan: ${planPath}`);
    console.log(`Title: ${plan.title}`);
    console.log(`Brand: ${plan.brand}`);
    console.log(`Formatting requests: ${plan.requests.length}`);
    console.log(`Tables: ${plan.tables.length}`);

    if (dryRun) {
        console.log('\n[DRY RUN] Would execute the following steps:');
        console.log('  1. Create document');
        console.log('  2. Insert text content');
        console.log(`  3. Apply ${plan.requests.length} formatting requests`);
        console.log(`  4. Insert ${plan.tables.length} tables`);
        if (plan.header_footer?.header) console.log('  5. Set header/footer');
        return;
    }

    // Step 1: Create the document from the appropriate template
    // - Letterhead: pre-configured header with company info, no page numbers
    // - Page numbers: pre-configured footer with auto-updating page numbers
    // - Default: blank document
    const isLetterhead = plan.templateType === 'doc-letterhead';
    const usePageNumTemplate = !isLetterhead && plan.header_footer?.pageNumbers !== false;
    let documentId;
    let templateLabel = '';

    // Resolve template IDs: prefer googleDocTemplates from composed template, fall back to constants
    const pageNumTemplateId = plan.googleDocTemplates?.pageNumber || PAGE_NUM_TEMPLATE_ID_FALLBACK;
    const letterheadTemplateId = plan.googleDocTemplates?.letterhead;

    if (isLetterhead) {
        if (!letterheadTemplateId) {
            const brand = plan.composedFrom?.brand || 'unknown';
            console.error(`\n❌ ERROR: No letterhead template ID for brand "${brand}".`);
            console.error(`   The composed template has googleDocTemplates.letterhead = null.`);
            console.error(`   This brand needs a letterhead starter template created first.`);
            console.error(`   Run: node compose-branded-template.js --brand ${plan.composedFrom?.brandSlug || brand} --all`);
            console.error(`   Or provide one manually: --google-doc-templates '{"letterhead":"<id>"}'`);
            process.exit(1);
        }
        documentId = createDocumentFromTemplate(plan.title, letterheadTemplateId);
        templateLabel = ' (from letterhead template)';
    } else if (usePageNumTemplate) {
        documentId = createDocumentFromTemplate(plan.title, pageNumTemplateId);
        templateLabel = ' (from page-number template)';
    } else {
        documentId = createDocument(plan.title);
    }
    console.log(`\nCreated document: ${documentId}${templateLabel}`);

    // Step 1b: Set document to PAGED mode if specified
    // Skip if created from template (already PAGED with correct margins)
    if (!isLetterhead && !usePageNumTemplate && plan.documentSettings?.pageMode === 'PAGED') {
        setPagedMode(documentId);
        console.log('Set document to PAGED mode');
    }

    // Step 1c: Clear template placeholder content (for template-based docs)
    // Templates like letterhead have placeholder text that must be removed
    // before inserting the real content.
    if (isLetterhead || usePageNumTemplate) {
        clearTemplateBody(documentId);
    }

    // Step 2: Insert all text content
    insertContent(documentId, plan.content);
    console.log('Inserted text content');

    // Step 3: Apply native bullets to list items
    if (plan.listItems && plan.listItems.length > 0) {
        applyNativeBullets(documentId, plan.listItems);
        console.log(`Applied native bullets to ${plan.listItems.length} list items`);
    }

    // Step 4: Apply all formatting in a single batchUpdate
    if (plan.requests.length > 0) {
        applyFormatting(documentId, plan.requests);
        console.log(`Applied ${plan.requests.length} formatting requests`);
    }

    // Step 5: Insert tables (replacing placeholders)
    if (plan.tables.length > 0) {
        insertTables(documentId, plan.tables, plan.tableStyle);
        console.log(`Inserted ${plan.tables.length} tables`);
    }

    // Step 5b: Optimize table column widths
    if (plan.tables.length > 0) {
        optimizeTableColumnWidths(documentId, plan.tables);
        console.log('Optimized table column widths');
    }

    // Step 5c: Apply compact formatting to dense tables (7+ columns)
    if (plan.tables.length > 0) {
        applyDenseTableFormatting(documentId);
        console.log('Applied dense table formatting');
    }

    // Step 5d: Insert visible page breaks before signature blocks, appendices, exhibits, schedules
    if (plan.pageBreaks?.indices?.length > 0) {
        insertVisiblePageBreaks(documentId, plan.pageBreaks.indices);
        console.log(`Inserted ${plan.pageBreaks.indices.length} page breaks`);
    }

    // Step 6: Set headers/footers
    // Skip for letterhead — the template already has the header configured
    // with company address, logo positioning, etc.
    if (plan.header_footer && !isLetterhead) {
        setHeaderWithLogo(documentId, plan.header_footer);
        console.log('Set header with logo');

        // Step 6b: Insert full logo image at top of first page (right-justified)
        // This compensates for the Docs API not supporting first-page-only headers
        insertFirstPageLogo(documentId, plan);

        // Page numbers are handled by the template (createDocumentFromTemplate)
        // which has pre-configured footer with auto-updating page numbers.
    }

    // Step 7: Orphan detection — runs LAST, after all content, tables, headers,
    // and logos are in place. This ensures the PDF export reflects the final layout.
    if (plan.pageBreaks?.orphanDetection !== false) {
        orphanDetection.fixOrphanedHeadings(documentId, plan);
        console.log('Checked for orphaned headings');
    } else {
        console.log('Orphan detection disabled for this template type');
    }

    // Step 7: Move to folder if specified
    if (folderId) {
        moveToFolder(documentId, folderId);
        console.log(`Moved to folder: ${folderId}`);
    }

    const url = `https://docs.google.com/document/d/${documentId}/edit`;
    console.log(`\nDocument URL: ${url}`);

    // Output JSON result for programmatic consumption
    const result = { documentId, url, title: plan.title };
    fs.writeFileSync('/dev/stdout', '\n' + JSON.stringify(result) + '\n');
}

// ============================================================================
// GWS CLI HELPERS
// ============================================================================

/**
 * Run a gws command and return parsed JSON response.
 * Uses stdin piping for request bodies to avoid shell quoting issues.
 */
function gws(service, resource, method, params, body, retries = 3) {
    let cmd = `gws ${service} ${resource} ${method}`;
    if (params) {
        cmd += ` --params '${JSON.stringify(params)}'`;
    }
    if (body) {
        const tmpFile = `/tmp/gws-body-${Date.now()}-${Math.random().toString(36).slice(2)}.json`;
        fs.writeFileSync(tmpFile, JSON.stringify(body));
        cmd += ` --json "$(cat ${tmpFile})"`;
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const result = execSync(cmd, {
                    encoding: 'utf8',
                    maxBuffer: 10 * 1024 * 1024,
                    shell: '/bin/bash'
                });
                fs.unlinkSync(tmpFile);
                return parseGwsOutput(result);
            } catch (err) {
                // Retry on rate limit (429)
                if (err.stdout && err.stdout.includes('429') && attempt < retries) {
                    const waitSec = 15 * (attempt + 1);
                    console.warn(`  Rate limited, waiting ${waitSec}s...`);
                    execSync(`sleep ${waitSec}`);
                    continue;
                }
                try { fs.unlinkSync(tmpFile); } catch (_) {}
                if (err.stdout) {
                    console.error(`gws error: ${err.stdout}`);
                }
                throw err;
            }
        }
    }
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const result = execSync(cmd, { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 });
            return parseGwsOutput(result);
        } catch (err) {
            if (err.stdout && err.stdout.includes('429') && attempt < retries) {
                const waitSec = 15 * (attempt + 1);
                console.warn(`  Rate limited, waiting ${waitSec}s...`);
                execSync(`sleep ${waitSec}`);
                continue;
            }
            throw err;
        }
    }
}

// Initialize orphan detection with shared dependencies
orphanDetection.init({ gws, fs, execSync });

/**
 * Parse gws output, filtering out non-JSON lines like "Using keyring backend: keyring".
 */
function parseGwsOutput(output) {
    const trimmed = output.trim();
    // Find the first '{' to skip any prefix lines
    const jsonStart = trimmed.indexOf('{');
    if (jsonStart === -1) {
        // Maybe it's an array response
        const arrStart = trimmed.indexOf('[');
        if (arrStart >= 0) return JSON.parse(trimmed.substring(arrStart));
        return {};
    }
    return JSON.parse(trimmed.substring(jsonStart));
}

// ============================================================================
// EXECUTION STEPS
// ============================================================================

/**
 * Step 5e: Insert visible page break characters before specific headings.
 *
 * Searches the actual document for heading paragraphs matching the trigger
 * patterns (appendix, exhibit, schedule, signature, in witness whereof)
 * and inserts a page break before each one.
 *
 * Must run AFTER table insertion since tables shift all indices.
 * Processes in reverse document order so insertions don't shift later ones.
 */
function insertVisiblePageBreaks(documentId, pageBreakEntries) {
    if (!pageBreakEntries || pageBreakEntries.length === 0) return;

    // Build a set of heading texts to match (lowercase for comparison)
    const targetTexts = new Set(pageBreakEntries.map(e => e.text.trim().toLowerCase()));

    // Fetch the actual document to get current indices
    const doc = gws('docs', 'documents', 'get', { documentId });
    const body = doc.body;
    if (!body || !body.content) return;

    // Find heading paragraphs that match our target texts
    const matches = [];
    for (const element of body.content) {
        if (!element.paragraph) continue;
        const ps = element.paragraph.paragraphStyle;
        if (!ps?.namedStyleType?.startsWith('HEADING')) continue;

        // Extract paragraph text
        let text = '';
        for (const pe of element.paragraph.elements || []) {
            if (pe.textRun?.content) text += pe.textRun.content;
        }
        text = text.trim();

        if (targetTexts.has(text.toLowerCase())) {
            matches.push({ index: element.startIndex, text });
        }
    }

    // Process in reverse order so insertions don't shift later indices
    matches.sort((a, b) => b.index - a.index);

    for (const match of matches) {
        // Insert a newline to create a new empty paragraph before the heading
        gws('docs', 'documents', 'batchUpdate', { documentId }, {
            requests: [{
                insertText: {
                    text: '\n',
                    location: { index: match.index }
                }
            }]
        });

        // Insert a page break in that new paragraph (at the same index, before the newline)
        gws('docs', 'documents', 'batchUpdate', { documentId }, {
            requests: [{
                insertPageBreak: {
                    location: { index: match.index }
                }
            }]
        });

        console.log(`  Page break before: "${match.text}"`);
    }
}

// Fallback Google Doc template IDs (Pvragon LLC > Templates > Agent Templates).
// Preferred: read from plan.googleDocTemplates (set by composed branded templates).
// These constants are kept for backward compatibility with older composed templates
// that don't yet have the googleDocTemplates field.
const PAGE_NUM_TEMPLATE_ID_FALLBACK = '1ece9BQ7ouVm0Zg-YCxGaM0REjPuz_yl4q8f1oYLH2i4';
const LETTERHEAD_TEMPLATE_ID_FALLBACK = '1R_mBGvrZfOdAz8bkFWtr4Rn_rsfJqU0q0VClf7YDV-A';

/**
 * Clear the body content of a template-created document.
 * Templates have placeholder text (e.g., "[Date]", "[Body of Letter]") that
 * must be removed before inserting real content. Preserves headers/footers.
 */
function clearTemplateBody(documentId) {
    const doc = gws('docs', 'documents', 'get', { documentId });
    const body = doc.body;
    if (!body || !body.content || body.content.length < 2) return;

    // Find the content range to delete (skip the first sectionBreak element)
    const firstContent = body.content[1]; // first element after sectionBreak
    const lastContent = body.content[body.content.length - 1];
    const startIndex = firstContent.startIndex;
    const endIndex = lastContent.endIndex - 1; // leave one char to avoid empty doc error

    if (endIndex <= startIndex) return;

    gws('docs', 'documents', 'batchUpdate', { documentId }, {
        requests: [{
            deleteContentRange: {
                range: { startIndex, endIndex }
            }
        }]
    });
}

/**
 * Step 1: Create an empty Google Doc.
 */
function createDocument(title) {
    const response = gws('docs', 'documents', 'create', null, { title });
    return response.documentId;
}

/**
 * Step 1 (alt): Create a Google Doc by copying the page-number template.
 * The template has footer with auto-updating page numbers and
 * "different first page" enabled (no page number on page 1).
 */
function createDocumentFromTemplate(title, templateId) {
    const response = gws('drive', 'files', 'copy', { fileId: templateId }, { name: title });
    return response.id;
}

/**
 * Step 1b: Set document to PAGED mode (vs PAGELESS default).
 * Uses documentFormat.documentMode which is the actual pageless/paged toggle.
 */
function setPagedMode(documentId) {
    gws('docs', 'documents', 'batchUpdate', { documentId }, {
        requests: [{
            updateDocumentStyle: {
                documentStyle: {
                    documentFormat: {
                        documentMode: "PAGES"
                    },
                    pageSize: {
                        height: { magnitude: 792, unit: "PT" },
                        width: { magnitude: 612, unit: "PT" }
                    },
                    marginTop: { magnitude: 72, unit: "PT" },
                    marginBottom: { magnitude: 72, unit: "PT" },
                    marginLeft: { magnitude: 72, unit: "PT" },
                    marginRight: { magnitude: 72, unit: "PT" }
                },
                fields: "documentFormat,pageSize,marginTop,marginBottom,marginLeft,marginRight"
            }
        }]
    });
}

/**
 * Step 2: Insert all text content at index 1.
 */
function insertContent(documentId, content) {
    const requests = [{
        insertText: {
            text: content,
            location: { index: 1 }
        }
    }];
    gws('docs', 'documents', 'batchUpdate', { documentId }, { requests });
}

/**
 * Step 3: Apply all formatting requests in a single batchUpdate call.
 */
function applyFormatting(documentId, requests) {
    // Google Docs API has a limit on request size, so batch in chunks of 500
    const CHUNK_SIZE = 500;
    for (let i = 0; i < requests.length; i += CHUNK_SIZE) {
        const chunk = requests.slice(i, i + CHUNK_SIZE);
        gws('docs', 'documents', 'batchUpdate', { documentId }, { requests: chunk });
    }
}

/**
 * Step 4: Insert tables by replacing placeholders.
 *
 * Strategy: For each table, find the placeholder text position in the
 * current document, delete it, and insert a table at that position.
 * Process tables in reverse order to preserve earlier indices.
 */
function insertTables(documentId, tables, tableStyle) {
    // Process tables in reverse order so earlier indices aren't affected
    for (let i = tables.length - 1; i >= 0; i--) {
        const table = tables[i];
        const numRows = table.rows.length + 1; // +1 for header row
        const numCols = table.headers.length;

        // Find and remove placeholder, then insert table
        // First, get the document to find the placeholder position
        const doc = gws('docs', 'documents', 'get', { documentId });
        const placeholderIndex = findPlaceholderIndex(doc, table.placeholder);

        if (placeholderIndex === -1) {
            console.warn(`  Warning: placeholder ${table.placeholder} not found, skipping table`);
            continue;
        }

        // Delete the placeholder text and its trailing newline
        const deleteRequests = [{
            deleteContentRange: {
                range: {
                    startIndex: placeholderIndex,
                    endIndex: placeholderIndex + table.placeholder.length + 1 // +1 for newline
                }
            }
        }];
        gws('docs', 'documents', 'batchUpdate', { documentId }, { requests: deleteRequests });

        // Insert table at that position
        const insertRequests = [{
            insertTable: {
                rows: numRows,
                columns: numCols,
                location: { index: placeholderIndex }
            }
        }];
        gws('docs', 'documents', 'batchUpdate', { documentId }, { requests: insertRequests });

        // Now populate the table cells
        // Re-fetch doc to get the table structure with correct indices
        const updatedDoc = gws('docs', 'documents', 'get', { documentId });
        populateTable(documentId, updatedDoc, placeholderIndex, table, tableStyle);
    }
}

/**
 * Find the character index of a placeholder string in the document body.
 */
function findPlaceholderIndex(doc, placeholder) {
    const body = doc.body;
    if (!body || !body.content) return -1;

    for (const element of body.content) {
        if (element.paragraph) {
            for (const pe of element.paragraph.elements || []) {
                if (pe.textRun && pe.textRun.content && pe.textRun.content.includes(placeholder)) {
                    return pe.startIndex;
                }
            }
        }
    }
    return -1;
}

/**
 * Populate a table's cells with header and row data.
 * Finds the table element near the given index and fills cells.
 *
 * Important: Each insertText shifts subsequent indices, so we must process
 * cells in reverse document order (last row last col → first row first col)
 * OR do one cell at a time. We batch all inserts in reverse order.
 */
function populateTable(documentId, doc, nearIndex, tableData, tableStyle) {
    const result = findTableNearIndex(doc, nearIndex);
    if (!result) {
        console.warn('  Warning: could not find inserted table in document');
        return;
    }
    const { table, startIndex: tableStartIndex } = result;

    // Collect all cell insertions with their indices, then sort in reverse
    // document order so earlier insertions don't shift later ones
    const insertions = [];

    // Header cells (row 0)
    if (table.tableRows && table.tableRows[0]) {
        const headerRow = table.tableRows[0];
        for (let col = 0; col < tableData.headers.length; col++) {
            const cell = headerRow.tableCells?.[col];
            const rawText = stripBoldMarkers(tableData.headers[col] || '');
            if (cell?.content?.[0]?.paragraph?.elements?.[0] && rawText) {
                const cellIndex = cell.content[0].paragraph.elements[0].startIndex;
                insertions.push({
                    index: cellIndex,
                    text: rawText,
                    bold: true // headers always bold
                });
            }
        }
    }

    // Data rows — detect **bold** markers in cell text
    for (let row = 0; row < tableData.rows.length; row++) {
        const tableRow = table.tableRows?.[row + 1]; // +1 to skip header
        if (!tableRow) continue;

        for (let col = 0; col < tableData.rows[row].length; col++) {
            const cell = tableRow.tableCells?.[col];
            if (cell?.content?.[0]?.paragraph?.elements?.[0]) {
                const cellIndex = cell.content[0].paragraph.elements[0].startIndex;
                const rawCellText = tableData.rows[row][col] || '';
                const { text: cleanText, boldRanges } = parseBoldInText(rawCellText);
                if (cleanText) {
                    insertions.push({
                        index: cellIndex,
                        text: cleanText,
                        bold: false,
                        boldRanges // relative offsets within the cell text
                    });
                }
            }
        }
    }

    // Sort in REVERSE index order so insertions don't shift each other
    insertions.sort((a, b) => b.index - a.index);

    const requests = [];
    for (const ins of insertions) {
        requests.push({
            insertText: {
                text: ins.text,
                location: { index: ins.index }
            }
        });
        if (ins.bold) {
            // Entire cell is bold (headers)
            requests.push({
                updateTextStyle: {
                    range: {
                        startIndex: ins.index,
                        endIndex: ins.index + ins.text.length
                    },
                    textStyle: { bold: true },
                    fields: "bold"
                }
            });
        } else if (ins.boldRanges && ins.boldRanges.length > 0) {
            // Partial bold from **markers** in cell text
            for (const br of ins.boldRanges) {
                requests.push({
                    updateTextStyle: {
                        range: {
                            startIndex: ins.index + br.start,
                            endIndex: ins.index + br.end
                        },
                        textStyle: { bold: true },
                        fields: "bold"
                    }
                });
            }
        }
    }

    if (requests.length > 0) {
        gws('docs', 'documents', 'batchUpdate', { documentId }, { requests });
    }

    // Apply header row styling (background color + white bold font) if tableStyle is configured
    // Re-fetch doc to get post-insertion indices for styling
    if (tableStyle && table.tableRows && table.tableRows[0]) {
        const freshDoc = gws('docs', 'documents', 'get', { documentId });
        const freshResult = findTableNearIndex(freshDoc, nearIndex);
        if (freshResult) {
            applyTableHeaderStyle(documentId, freshResult.table, freshResult.startIndex, tableStyle);
        }
    }
}

/**
 * Apply branded styling to the header row of a table:
 * - Background color on all header cells
 * - White bold font on header text
 * - 10pt spacing after the table paragraph
 */
function applyTableHeaderStyle(documentId, table, tableStartIndex, tableStyle) {
    const headerRow = table.tableRows[0];
    const styleRequests = [];
    const numCols = headerRow.tableCells?.length || 0;

    // Background color on entire header row at once
    // Support both old flat format (headerBackground) and new nested format (headerRow.background)
    const headerBg = tableStyle.headerRow?.background || tableStyle.headerBackground;
    if (headerBg && numCols > 0) {
        styleRequests.push({
            updateTableCellStyle: {
                tableRange: {
                    tableCellLocation: {
                        tableStartLocation: { index: tableStartIndex },
                        rowIndex: 0,
                        columnIndex: 0
                    },
                    rowSpan: 1,
                    columnSpan: numCols
                },
                tableCellStyle: {
                    backgroundColor: {
                        color: { rgbColor: hexToRgb(headerBg) }
                    }
                },
                fields: "backgroundColor"
            }
        });
    }

    // Bold text with configured color on all header cell content
    const headerFontColor = tableStyle.headerRow?.fontColor || tableStyle.headerFontColor;
    if (headerFontColor) {
        for (const cell of headerRow.tableCells || []) {
            for (const content of cell.content || []) {
                if (content.paragraph?.elements) {
                    for (const el of content.paragraph.elements) {
                        if (el.textRun && el.startIndex < el.endIndex) {
                            styleRequests.push({
                                updateTextStyle: {
                                    range: { startIndex: el.startIndex, endIndex: el.endIndex },
                                    textStyle: {
                                        bold: true,
                                        foregroundColor: { color: { rgbColor: hexToRgb(headerFontColor) } }
                                    },
                                    fields: "bold,foregroundColor"
                                }
                            });
                        }
                    }
                }
            }
        }
    }

    if (styleRequests.length > 0) {
        gws('docs', 'documents', 'batchUpdate', { documentId }, { requests: styleRequests });
    }
}

/**
 * Strip **bold** markers from text, returning clean text.
 */
function stripBoldMarkers(text) {
    return text.replace(/\*\*(.*?)\*\*/g, '$1');
}

/**
 * Parse **bold** markers in text, returning clean text and bold ranges.
 * Returns: { text: string, boldRanges: [{start, end}] }
 */
function parseBoldInText(rawText) {
    const boldRanges = [];
    let cleanText = '';
    let i = 0;

    while (i < rawText.length) {
        if (rawText[i] === '*' && rawText[i + 1] === '*') {
            // Find closing **
            const closeIdx = rawText.indexOf('**', i + 2);
            if (closeIdx !== -1) {
                const boldContent = rawText.substring(i + 2, closeIdx);
                const start = cleanText.length;
                cleanText += boldContent;
                boldRanges.push({ start, end: cleanText.length });
                i = closeIdx + 2;
                continue;
            }
        }
        cleanText += rawText[i];
        i++;
    }

    return { text: cleanText, boldRanges };
}

/**
 * Convert hex color string to Google Docs rgbColor.
 */
function hexToRgb(hex) {
    hex = hex.replace(/^#/, '');
    return {
        red: parseInt(hex.substring(0, 2), 16) / 255,
        green: parseInt(hex.substring(2, 4), 16) / 255,
        blue: parseInt(hex.substring(4, 6), 16) / 255
    };
}

/**
 * Find a table element in the document body near a given index.
 * Returns { table, startIndex } so callers can reference the table's body position.
 */
function findTableNearIndex(doc, nearIndex) {
    const body = doc.body;
    if (!body || !body.content) return null;

    for (const element of body.content) {
        if (element.table && element.startIndex >= nearIndex - 2) {
            return { table: element.table, startIndex: element.startIndex };
        }
    }
    return null;
}

/**
 * Step 3: Apply native Google Docs bullets to list item paragraphs.
 * Groups contiguous list items and applies createParagraphBullets.
 * Uses nestingLevel for nested bullets (no text-based indentation).
 */
function applyNativeBullets(documentId, listItems) {
    if (!listItems || listItems.length === 0) return;

    const requests = [];

    for (const item of listItems) {
        // createParagraphBullets converts paragraphs to bullet/numbered lists
        requests.push({
            createParagraphBullets: {
                range: { startIndex: item.startIndex, endIndex: item.endIndex },
                bulletPreset: item.ordered ? 'NUMBERED_DECIMAL_ALPHA_ROMAN' : 'BULLET_DISC_CIRCLE_SQUARE'
            }
        });

        // Set nesting level for sub-bullets
        if (item.level > 0) {
            requests.push({
                updateParagraphStyle: {
                    range: { startIndex: item.startIndex, endIndex: item.endIndex },
                    paragraphStyle: {
                        indentStart: { magnitude: 36 * item.level, unit: "PT" },
                        indentFirstLine: { magnitude: 36 * item.level - 18, unit: "PT" }
                    },
                    fields: "indentStart,indentFirstLine"
                }
            });
        }
    }

    if (requests.length > 0) {
        gws('docs', 'documents', 'batchUpdate', { documentId }, { requests });
    }
}

/**
 * Step 5b: Optimize table column widths.
 * Strategy: ensure short-word columns (where the longest word is short) get
 * enough width to avoid mid-word wrapping, then distribute remaining space
 * proportionally to columns with longer content.
 *
 * Algorithm:
 *   1. For each column, find the longest single word across all cells.
 *   2. Compute a "minimum comfortable width" = longest_word_chars * avg_char_width + padding.
 *      This prevents mid-word wrapping for columns with short values like "Complete" or "$120K".
 *   3. Allocate minimum widths first, then distribute remaining page width
 *      proportionally based on max cell content length.
 *
 * Uses available page width: 468pt = 612pt page - 2×72pt margins.
 */
function optimizeTableColumnWidths(documentId, tables) {
    const PAGE_WIDTH_PT = 468;
    const CELL_PADDING_PT = 14;    // horizontal padding inside cells

    const doc = gws('docs', 'documents', 'get', { documentId });
    const body = doc.body;
    if (!body || !body.content) return;

    const docTables = body.content.filter(el => el.table);

    for (const element of docTables) {
        const table = element.table;
        if (!table.tableRows || table.tableRows.length === 0) continue;

        const numCols = table.columns || table.tableRows[0].tableCells?.length || 0;
        if (numCols === 0) continue;

        // Use different char width for dense vs normal tables
        const isDense = numCols >= 6;
        const charWidth = isDense ? 5.0 : 6.5; // 8pt font vs 10pt font

        // Gather per-column metrics
        const colMaxChars = new Array(numCols).fill(0);      // longest cell content
        const colLongestWord = new Array(numCols).fill(0);    // longest single word

        for (const row of table.tableRows) {
            for (let col = 0; col < numCols; col++) {
                const cell = row.tableCells?.[col];
                if (!cell) continue;

                let cellText = '';
                for (const content of cell.content || []) {
                    if (content.paragraph?.elements) {
                        for (const el of content.paragraph.elements) {
                            if (el.textRun?.content) {
                                cellText += el.textRun.content;
                            }
                        }
                    }
                }
                const trimmed = cellText.trim();
                const cleaned = stripBoldMarkers(trimmed);
                colMaxChars[col] = Math.max(colMaxChars[col], cleaned.length);

                // Find longest word (split on spaces, hyphens, slashes)
                const words = cleaned.split(/[\s\-\/]+/);
                for (const word of words) {
                    colLongestWord[col] = Math.max(colLongestWord[col], word.length);
                }
            }
        }

        // Step 1: Compute minimum width — must fit longest word without breaking
        const colMinWidth = colLongestWord.map(
            wordLen => Math.ceil(wordLen * charWidth) + CELL_PADDING_PT
        );

        // Step 2: Compute natural width (fits longest cell content on one line)
        const colNaturalWidth = colMaxChars.map(
            chars => Math.ceil(chars * charWidth) + CELL_PADDING_PT
        );

        // Step 3: Start with natural widths (content-fitted)
        const colWidths = colMinWidth.map((minW, i) => Math.max(minW, colNaturalWidth[i]));

        // Step 4: If total exceeds page width, scale down but protect minimum widths
        const totalWidth = colWidths.reduce((sum, w) => sum + w, 0);
        if (totalWidth > PAGE_WIDTH_PT) {
            // First try: give every column its minimum, distribute remainder to larger columns
            const totalMin = colMinWidth.reduce((sum, w) => sum + w, 0);
            const surplus = Math.max(0, PAGE_WIDTH_PT - totalMin);
            const totalExtra = colNaturalWidth.reduce((sum, w, i) => sum + Math.max(0, w - colMinWidth[i]), 0);

            for (let i = 0; i < numCols; i++) {
                if (totalExtra > 0 && surplus > 0) {
                    const extra = Math.max(0, colNaturalWidth[i] - colMinWidth[i]);
                    colWidths[i] = colMinWidth[i] + Math.round((extra / totalExtra) * surplus);
                } else {
                    colWidths[i] = colMinWidth[i];
                }
            }

            // If still over (too many columns), scale everything proportionally as last resort
            const finalTotal = colWidths.reduce((sum, w) => sum + w, 0);
            if (finalTotal > PAGE_WIDTH_PT) {
                const scale = PAGE_WIDTH_PT / finalTotal;
                for (let i = 0; i < numCols; i++) {
                    colWidths[i] = Math.round(colWidths[i] * scale);
                }
            }
        }

        const requests = [];
        for (let col = 0; col < numCols; col++) {
            requests.push({
                updateTableColumnProperties: {
                    tableStartLocation: { index: element.startIndex },
                    columnIndices: [col],
                    tableColumnProperties: {
                        widthType: "FIXED_WIDTH",
                        width: { magnitude: Math.max(colWidths[col], 24), unit: "PT" }
                    },
                    fields: "widthType,width"
                }
            });
        }

        if (requests.length > 0) {
            gws('docs', 'documents', 'batchUpdate', { documentId }, { requests });
        }
    }
}


// Orphan detection is in lib/orphan-detection.js (v1.0.0, frozen)
// Called via orphanDetection.fixOrphanedHeadings(documentId, plan)

/**
 * Step 5c: Apply compact formatting to dense tables (7+ columns).
 * Reduces font size to 8pt and tightens cell padding to fit content.
 */
function applyDenseTableFormatting(documentId) {
    const DENSE_COL_THRESHOLD = 6;

    const doc = gws('docs', 'documents', 'get', { documentId });
    const body = doc.body;
    if (!body || !body.content) return;

    const docTables = body.content.filter(el => el.table);

    for (const element of docTables) {
        const table = element.table;
        if (!table.tableRows || table.tableRows.length === 0) continue;

        const numCols = table.columns || table.tableRows[0].tableCells?.length || 0;
        if (numCols < DENSE_COL_THRESHOLD) continue;

        const requests = [];

        // Reduce font size in all cells to 8pt
        for (const row of table.tableRows) {
            for (const cell of row.tableCells || []) {
                for (const content of cell.content || []) {
                    if (content.paragraph?.elements) {
                        for (const el of content.paragraph.elements) {
                            if (el.textRun && el.startIndex !== undefined && el.endIndex !== undefined && el.startIndex < el.endIndex) {
                                requests.push({
                                    updateTextStyle: {
                                        range: { startIndex: el.startIndex, endIndex: el.endIndex },
                                        textStyle: {
                                            fontSize: { magnitude: 8, unit: "PT" }
                                        },
                                        fields: "fontSize"
                                    }
                                });
                            }
                        }
                    }
                }
            }
        }

        // Reduce cell padding on all cells
        const numRows = table.tableRows.length;
        for (let row = 0; row < numRows; row++) {
            for (let col = 0; col < numCols; col++) {
                requests.push({
                    updateTableCellStyle: {
                        tableRange: {
                            tableCellLocation: {
                                tableStartLocation: { index: element.startIndex },
                                rowIndex: row,
                                columnIndex: col
                            },
                            rowSpan: 1,
                            columnSpan: 1
                        },
                        tableCellStyle: {
                            paddingTop: { magnitude: 2, unit: "PT" },
                            paddingBottom: { magnitude: 2, unit: "PT" },
                            paddingLeft: { magnitude: 4, unit: "PT" },
                            paddingRight: { magnitude: 4, unit: "PT" }
                        },
                        fields: "paddingTop,paddingBottom,paddingLeft,paddingRight"
                    }
                });
            }
        }

        if (requests.length > 0) {
            // Batch in chunks to avoid request size limits
            const CHUNK_SIZE = 500;
            for (let i = 0; i < requests.length; i += CHUNK_SIZE) {
                const chunk = requests.slice(i, i + CHUNK_SIZE);
                gws('docs', 'documents', 'batchUpdate', { documentId }, { requests: chunk });
            }
        }
    }
}

/**
 * Step 6: Create headers with favicon/icon logo (pages 2+).
 *
 * Uses useFirstPageHeaderFooter to hide the header on page 1. The Docs API
 * doesn't support creating first-page headers, so the first page header
 * stays empty — effectively showing the favicon on pages 2+ only.
 * The full logo is inserted into the document body on page 1 instead
 * (see insertFirstPageLogo).
 */
function setHeaderWithLogo(documentId, headerFooter) {
    const showFirst = headerFooter.showOnFirstPage !== false;
    const showSubsequent = headerFooter.showOnSubsequentPages !== false;

    // No header at all
    if (!showFirst && !showSubsequent) {
        console.log('  No header configured for this template');
        return;
    }

    // Create DEFAULT header (shows on all pages initially)
    const createResponse = gws('docs', 'documents', 'batchUpdate', { documentId }, {
        requests: [{ createHeader: { type: "DEFAULT", sectionBreakLocation: { index: 0 } } }]
    });
    const headerId = createResponse.replies?.[0]?.createHeader?.headerId;
    if (!headerId) {
        console.warn('  Warning: could not create header');
        return;
    }

    // Determine which logo to put in the persistent header
    const subsequentLogoPath = headerFooter.subsequentLogoPath;
    const hasSubsequentLogo = subsequentLogoPath && fs.existsSync(subsequentLogoPath);
    const firstLogoPath = headerFooter.logoPath;
    const hasFirstLogo = firstLogoPath && fs.existsSync(firstLogoPath);

    if (hasSubsequentLogo) {
        const dims = headerFooter.subsequentLogoDimensions || { width: 24, height: 24 };
        insertLogoInHeader(documentId, headerId, subsequentLogoPath, dims);
    } else if (hasFirstLogo) {
        const dims = headerFooter.logoDimensions || { width: 150, height: 23 };
        insertLogoInHeader(documentId, headerId, firstLogoPath, dims);
    }

    // Enable "different first page" so the DEFAULT header only shows on pages 2+.
    // The first-page header stays empty (API can't create it), which is what we want —
    // the full logo gets inserted into the body instead.
    if (hasSubsequentLogo && hasFirstLogo) {
        gws('docs', 'documents', 'batchUpdate', { documentId }, {
            requests: [{
                updateDocumentStyle: {
                    documentStyle: { useFirstPageHeaderFooter: true },
                    fields: "useFirstPageHeaderFooter"
                }
            }]
        });
        console.log('  Inserted favicon in header (pages 2+), first page header hidden');
    } else {
        console.log('  Inserted logo in header (all pages)');
    }
}

/**
 * Step 6b: Insert full logo image at the top of page 1.
 *
 * Workaround for the Google Docs API not supporting first-page-only headers.
 * Inserts the full logo as an inline image at index 1 with right alignment,
 * negative space above (-18pt) to pull it up near the top margin, and 12pt
 * space after to separate from document content.
 */
function insertFirstPageLogo(documentId, plan) {
    const hf = plan.header_footer;
    if (!hf) return;

    const logoPath = hf.logoPath;
    if (!logoPath || !fs.existsSync(logoPath)) return;

    // Also need a subsequent logo to justify this workaround
    // (if there's no favicon, the full logo is already in the header for all pages)
    const hasSubsequentLogo = hf.subsequentLogoPath && fs.existsSync(hf.subsequentLogoPath);
    if (!hasSubsequentLogo) return;

    // Upload logo to Drive
    const logoFileName = `_logo_firstpage_${Date.now()}.png`;
    const uploadResult = execSync(
        `gws drive files create --json '{"name":"${logoFileName}","mimeType":"image/png"}' --upload "${logoPath}"`,
        { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
    );
    const uploadData = parseGwsOutput(uploadResult);
    const logoFileId = uploadData.id;
    if (!logoFileId) return;

    // Make publicly readable
    try {
        execSync(
            `gws drive permissions create --params '{"fileId":"${logoFileId}"}' --json '{"role":"reader","type":"anyone"}'`,
            { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
        );
    } catch (e) {
        console.warn('  Warning: could not set first-page logo permissions');
    }

    const logoUrl = `https://drive.google.com/uc?id=${logoFileId}`;
    const rawDims = hf.logoDimensions || { width: 150, height: 23 };
    // Scale down the first-page body logo to 75% of the header logo size
    const dims = { width: Math.round(rawDims.width * 0.75), height: Math.round(rawDims.height * 0.75) };

    // Insert a newline at index 1 first, then insert the image before it
    gws('docs', 'documents', 'batchUpdate', { documentId }, {
        requests: [{
            insertText: {
                text: '\n',
                location: { index: 1 }
            }
        }]
    });

    // Insert logo image at index 1
    gws('docs', 'documents', 'batchUpdate', { documentId }, {
        requests: [{
            insertInlineImage: {
                location: { index: 1 },
                uri: logoUrl,
                objectSize: {
                    height: { magnitude: dims.height, unit: "PT" },
                    width: { magnitude: dims.width, unit: "PT" }
                }
            }
        }]
    });

    // Style the logo paragraph: right-aligned, pull up, space after
    gws('docs', 'documents', 'batchUpdate', { documentId }, {
        requests: [{
            updateParagraphStyle: {
                range: { startIndex: 1, endIndex: 3 },
                paragraphStyle: {
                    alignment: "END",
                    spaceAbove: { magnitude: 0, unit: "PT" },
                    spaceBelow: { magnitude: 12, unit: "PT" }
                },
                fields: "alignment,spaceAbove,spaceBelow"
            }
        }]
    });

    // Clean up uploaded logo
    try {
        execSync(
            `gws drive files delete --params '{"fileId":"${logoFileId}"}'`,
            { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
        );
    } catch (_) {}

    console.log('  Inserted full logo on first page (right-aligned, body top)');
}


/**
 * Upload a logo to Drive and insert it as an inline image in a header segment.
 * Handles upload, permissions, insertion, right-alignment, and cleanup.
 */
function insertLogoInHeader(documentId, headerId, logoPath, dims) {
    // Get header content index
    const doc = gws('docs', 'documents', 'get', { documentId });
    const headerContent = doc.headers?.[headerId];
    if (!headerContent?.content?.[0]) return;

    const idx = headerContent.content[0].startIndex;

    // Upload logo to Drive
    const logoFileName = `_logo_${Date.now()}_${Math.random().toString(36).slice(2)}.png`;
    const uploadResult = execSync(
        `gws drive files create --json '{"name":"${logoFileName}","mimeType":"image/png"}' --upload "${logoPath}"`,
        { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
    );
    const uploadData = parseGwsOutput(uploadResult);
    const logoFileId = uploadData.id;
    if (!logoFileId) return;

    // Make publicly readable
    try {
        execSync(
            `gws drive permissions create --params '{"fileId":"${logoFileId}"}' --json '{"role":"reader","type":"anyone"}'`,
            { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
        );
    } catch (e) {
        console.warn('  Warning: could not set logo permissions');
    }

    const logoUrl = `https://drive.google.com/uc?id=${logoFileId}`;

    // Insert inline image
    gws('docs', 'documents', 'batchUpdate', { documentId }, {
        requests: [{
            insertInlineImage: {
                location: { segmentId: headerId, index: idx },
                uri: logoUrl,
                objectSize: {
                    height: { magnitude: dims.height, unit: "PT" },
                    width: { magnitude: dims.width, unit: "PT" }
                }
            }
        }]
    });

    // Right-align the header paragraph
    try {
        const updatedDoc = gws('docs', 'documents', 'get', { documentId });
        const updatedHeader = updatedDoc.headers?.[headerId];
        if (updatedHeader?.content) {
            for (const el of updatedHeader.content) {
                if (el.paragraph && el.endIndex !== undefined) {
                    gws('docs', 'documents', 'batchUpdate', { documentId }, {
                        requests: [{
                            updateParagraphStyle: {
                                range: {
                                    segmentId: headerId,
                                    startIndex: el.startIndex || 0,
                                    endIndex: el.endIndex
                                },
                                paragraphStyle: {
                                    alignment: "END",
                                    spaceAbove: { magnitude: 0, unit: "PT" },
                                    spaceBelow: { magnitude: 10, unit: "PT" }
                                },
                                fields: "alignment,spaceAbove,spaceBelow"
                            }
                        }]
                    });
                    break;
                }
            }
        }
    } catch (e) {
        console.warn('  Warning: could not right-align header logo');
    }

    // Clean up uploaded logo file
    try {
        execSync(
            `gws drive files delete --params '{"fileId":"${logoFileId}"}'`,
            { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
        );
    } catch (_) { /* non-critical cleanup */ }
}

/**
 * Move a file to a specific Drive folder.
 */
function moveToFolder(documentId, folderId) {
    // Get current parents
    const file = gws('drive', 'files', 'get', {
        fileId: documentId,
        fields: 'parents'
    });

    const currentParents = (file.parents || []).join(',');

    gws('drive', 'files', 'update', {
        fileId: documentId,
        addParents: folderId,
        removeParents: currentParents,
        fields: 'id,parents'
    });
}

main();
