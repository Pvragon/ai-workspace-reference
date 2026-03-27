/**
 * Orphan Heading Detection (PDF + Docs API hybrid)
 * @version 1.0.0 — FROZEN
 * @date 2026-03-19
 *
 * Detects and fixes orphaned headings in Google Docs by cross-referencing
 * PDF page boundaries (visual layout) with the Docs API document structure
 * (semantic content).
 *
 * This module is intentionally frozen. It was validated against both legal
 * (doc-legal: SOW with 23 tables, numbered sections, signature blocks) and
 * report (doc-report: investment summary with 11 tables, nested headings)
 * document types. Changes should be made with extreme care.
 *
 * Dependencies: gws() helper, fs, execSync — injected via init().
 */

let gws, fs, execSync;

/**
 * Initialize module dependencies. Must be called before any other function.
 * @param {Object} deps - { gws, fs, execSync }
 */
function init(deps) {
    gws = deps.gws;
    fs = deps.fs;
    execSync = deps.execSync;
}

/**
 * Fix orphaned headings using PDF-based layout analysis.
 *
 * Instead of estimating element heights (unreliable), this exports the
 * document as PDF and reads actual page boundaries from Google's rendering
 * engine. An orphaned heading is one that appears in the last few lines
 * of a page with insufficient content after it.
 *
 * Algorithm:
 *   1. Export doc as PDF, extract text with page boundaries via pdftotext
 *   2. For each page, check if a heading appears in the last 8 lines
 *      with insufficient content after it
 *   3. Find that heading in the Docs API document. If consecutive headings
 *      precede it, walk backward to find the top of the group.
 *   4. Insert a visible page break before the group leader.
 *   5. Repeat from step 1 (re-export, since the page layout changed)
 *   6. Stop when a full pass finds no orphans or 20 passes reached
 */
function fixOrphanedHeadings(documentId, plan) {
    const MAX_PASSES = 20;
    let fixes = 0;

    // Wait briefly for Google's servers to finalize document reflow
    // after table insertion and formatting. Without this, the PDF export
    // may return a stale layout.
    execSync('sleep 5');

    // Build set of actual heading texts from the document (semantic truth)
    const knownHeadings = buildHeadingTextSet(documentId);

    // Track headings we've already fixed to prevent infinite loops.
    // A heading that's still "orphaned" after a page break was inserted
    // before it is likely followed by a table or other content that
    // pdftotext doesn't render as body text — re-fixing won't help.
    const alreadyFixed = new Set();

    for (let pass = 0; pass < MAX_PASSES; pass++) {
        const orphan = findFirstOrphanViaPdf(documentId, knownHeadings, alreadyFixed);

        if (!orphan) {
            if (fixes > 0) {
                console.log(`  Orphan detection complete after ${fixes} fix(es)`);
            } else {
                console.log('  No orphaned headings found');
            }
            break;
        }

        // Find the heading's index in the document, and walk backward
        // through any consecutive heading group to find the top.
        // E.g., if "3.1 Key Milestones" is orphaned and "3. Milestones
        // and Schedule" is directly before it (no content in between),
        // the break goes before "3. Milestones and Schedule".
        const doc = gws('docs', 'documents', 'get', { documentId });

        let breakTarget = orphan.text;
        const bodyContent = doc.body?.content || [];

        // Find the orphaned heading in the doc structure
        let orphanIdx = -1;
        for (let ei = 0; ei < bodyContent.length; ei++) {
            const el = bodyContent[ei];
            if (!el.paragraph) continue;
            const ps = el.paragraph.paragraphStyle;
            if (!ps?.namedStyleType?.startsWith('HEADING')) continue;
            let text = '';
            for (const pe of el.paragraph.elements || []) {
                if (pe.textRun?.content) text += pe.textRun.content;
            }
            if (text.trim().toLowerCase() === orphan.text.trim().toLowerCase()) {
                orphanIdx = ei;
                break;
            }
        }

        // Walk backward: if the element directly before this heading is
        // also a heading (with no content between), it's part of the group
        if (orphanIdx > 0) {
            for (let ei = orphanIdx - 1; ei >= 0; ei--) {
                const prev = bodyContent[ei];
                if (!prev.paragraph) break;
                const ps = prev.paragraph.paragraphStyle;
                if (!ps?.namedStyleType?.startsWith('HEADING')) break;
                // It's a heading — check if it has text
                let prevText = '';
                for (const pe of prev.paragraph.elements || []) {
                    if (pe.textRun?.content) prevText += pe.textRun.content;
                }
                if (prevText.trim()) {
                    breakTarget = prevText.trim();
                    // Keep walking — there might be more headings above
                } else {
                    // Empty heading paragraph (e.g., from HR rendering) — skip it
                    continue;
                }
            }
        }

        const headingIndex = findHeadingIndex(doc, breakTarget);

        if (headingIndex === null) {
            console.warn(`  Warning: could not locate heading "${breakTarget}", skipping`);
            knownHeadings.delete(orphan.text.trim().toLowerCase());
            continue;
        }

        // Insert visible page break
        gws('docs', 'documents', 'batchUpdate', { documentId }, {
            requests: [{ insertText: { text: '\n', location: { index: headingIndex } } }]
        });
        gws('docs', 'documents', 'batchUpdate', { documentId }, {
            requests: [{ insertPageBreak: { location: { index: headingIndex } } }]
        });

        fixes++;
        // Mark both the orphan and the break target as fixed
        alreadyFixed.add(orphan.text.trim().toLowerCase());
        alreadyFixed.add(breakTarget.trim().toLowerCase());
        if (breakTarget !== orphan.text) {
            console.log(`  [fix ${fixes}] Page break before "${breakTarget}" (group with "${orphan.text}", page ${orphan.page})`);
        } else {
            console.log(`  [fix ${fixes}] Page break before "${orphan.text}" (page ${orphan.page})`);
        }
    }
}

/**
 * Build a set of all heading texts from the document via the Docs API.
 * This gives us semantic truth about what's a heading vs body text.
 */
function buildHeadingTextSet(documentId) {
    const doc = gws('docs', 'documents', 'get', { documentId });
    const headings = new Set();

    for (const element of doc.body?.content || []) {
        if (!element.paragraph) continue;
        const ps = element.paragraph.paragraphStyle;
        if (!ps?.namedStyleType?.startsWith('HEADING')) continue;

        let text = '';
        for (const el of element.paragraph.elements || []) {
            if (el.textRun?.content) text += el.textRun.content;
        }
        const trimmed = text.trim();
        if (trimmed) {
            headings.add(trimmed.toLowerCase());
        }
    }

    return headings;
}

/**
 * Find the first orphaned heading using a hybrid approach:
 *   - PDF export for page boundaries (where does each page end?)
 *   - Docs API for document structure (what follows each heading?)
 *
 * A heading is orphaned if:
 *   1. It appears in the last 8 lines of a PDF page (near bottom)
 *   2. Its next sibling is a table: only orphaned if table is large (>3 rows)
 *      and only the header row is visible on this page
 *   3. Its section has a table: short PDF lines (< 30 chars) are discounted
 *      as likely table cells, not real body text
 *   4. The remaining content on the same PDF page after it has < 3 lines
 *      or < 50 chars (excluding heading text and discounted table cells)
 *
 * Note: consecutive headings are NOT skipped here. If a heading in a group
 * is orphaned, it's detected. The caller (fixOrphanedHeadings) walks backward
 * to find the top of the group and inserts the break there.
 *
 * Returns { text, page } or null if none found.
 */
function findFirstOrphanViaPdf(documentId, knownHeadings, alreadyFixed = new Set()) {
    // Export as PDF
    const pdfPath = `/tmp/orphan-check-${documentId.substring(0, 8)}.pdf`;
    const txtPath = pdfPath.replace('.pdf', '.txt');

    try {
        gws('drive', 'files', 'export', {
            fileId: documentId,
            mimeType: 'application/pdf'
        });
    } catch (e) {
        console.warn('  Warning: PDF export failed');
        return null;
    }

    if (!fs.existsSync('download.pdf')) {
        console.warn('  Warning: download.pdf not found after export');
        return null;
    }
    fs.renameSync('download.pdf', pdfPath);

    try {
        execSync(`pdftotext "${pdfPath}" "${txtPath}"`, { encoding: 'utf8' });
    } catch (e) {
        console.warn('  Warning: pdftotext failed');
        return null;
    }

    const text = fs.readFileSync(txtPath, 'utf8');
    const pages = text.split('\f');

    try { fs.unlinkSync(pdfPath); } catch (_) {}
    try { fs.unlinkSync(txtPath); } catch (_) {}

    // Get the actual document structure from Docs API
    const doc = gws('docs', 'documents', 'get', { documentId });
    const body = doc.body;
    if (!body || !body.content) return null;

    // Build ordered list of structural elements: headings, tables, paragraphs
    // This gives us the REAL document structure, not PDF text guesses
    const structuralElements = [];
    for (const element of body.content) {
        if (element.table) {
            structuralElements.push({
                kind: 'table',
                startIndex: element.startIndex,
                endIndex: element.endIndex
            });
        } else if (element.paragraph) {
            const ps = element.paragraph.paragraphStyle;
            const isHeading = ps?.namedStyleType?.startsWith('HEADING');
            let pText = '';
            for (const el of element.paragraph.elements || []) {
                if (el.textRun?.content) pText += el.textRun.content;
            }
            pText = pText.trim();

            if (isHeading && pText) {
                structuralElements.push({
                    kind: 'heading',
                    text: pText,
                    startIndex: element.startIndex,
                    endIndex: element.endIndex
                });
            } else if (pText) {
                structuralElements.push({
                    kind: 'paragraph',
                    text: pText,
                    startIndex: element.startIndex,
                    endIndex: element.endIndex
                });
            }
        }
    }

    // Build maps: for each heading, what are its next and previous siblings?
    const headingNextSibling = new Map();
    const headingPrevSibling = new Map();
    for (let i = 0; i < structuralElements.length; i++) {
        const el = structuralElements[i];
        if (el.kind !== 'heading') continue;

        // Look ahead for the next structural element
        for (let j = i + 1; j < structuralElements.length; j++) {
            headingNextSibling.set(el.text.toLowerCase(), structuralElements[j]);
            break;
        }
        // Look behind for the previous structural element
        for (let j = i - 1; j >= 0; j--) {
            headingPrevSibling.set(el.text.toLowerCase(), structuralElements[j]);
            break;
        }
    }

    // Build heading elements list for PDF text matching
    const headingElements = structuralElements
        .filter(e => e.kind === 'heading')
        .map(e => ({ text: e.text, startIndex: e.startIndex, endIndex: e.endIndex }));

    // For each page, check if any heading appears in the last 8 lines
    for (let i = 0; i < pages.length; i++) {
        const pageNum = i + 1;
        const lines = pages[i].split('\n').filter(l => l.trim());
        if (lines.length < 3) continue;

        const contentLines = lines.filter(l => !/^\d+$/.test(l.trim()));
        if (contentLines.length < 2) continue;

        const lastLines = contentLines.slice(-8);

        for (let j = 0; j < lastLines.length; j++) {
            const line = lastLines[j].trim();
            const lineLower = line.toLowerCase();

            // Find matching heading element from the Docs API
            const matchedHeading = headingElements.find(h =>
                h.text.toLowerCase() === lineLower ||
                (lineLower.length >= 15 && h.text.toLowerCase().startsWith(lineLower))
            );

            if (!matchedHeading) continue;

            // Skip headings we've already inserted a page break before
            if (alreadyFixed.has(matchedHeading.text.trim().toLowerCase())) continue;

            // --- Structural checks using Docs API (not PDF text) ---

            const nextSibling = headingNextSibling.get(matchedHeading.text.toLowerCase());

            // Rule: if a heading is followed by a table, check whether
            // enough of the table actually renders on this page.
            if (nextSibling?.kind === 'table') {
                const tableEl = body.content.find(e =>
                    e.table && e.startIndex === nextSibling.startIndex);
                const rowCount = tableEl?.table?.rows || 0;
                const colCount = tableEl?.table?.columns || 3;

                // Small tables (≤ 3 rows) are compact heading+table units.
                // Never orphan these — breaking before them creates more
                // whitespace damage than the orphan itself.
                if (rowCount <= 3) continue;

                // For larger tables, check if more than just the header row
                // is visible on this page. pdftotext renders each cell as
                // a line, so colCount lines = 1 row.
                let tableLines = 0;
                for (let k = j + 1; k < lastLines.length; k++) {
                    const afterLine = lastLines[k].trim();
                    if (!afterLine) continue;
                    const afterLower = afterLine.toLowerCase();
                    if (headingElements.some(h => h.text.toLowerCase() === afterLower)) continue;
                    tableLines++;
                }
                // Need more than one row (header) worth of lines visible.
                if (tableLines > colCount) continue;
                // Otherwise fall through — only header row visible = orphaned
            }

            // Note: we do NOT skip back-to-back headings here. If a heading
            // is orphaned, we detect it regardless. The fixOrphanedHeadings
            // function will walk backward to find the top of any heading
            // group and insert the break before the whole group.

            // --- PDF-based content check for remaining cases ---
            // For headings followed by paragraphs, check if there's enough
            // content remaining on this page after the heading.
            //
            // Use the Docs API structure to detect if a table appears within
            // this heading's section (between this heading and the next one).
            // If so, table content in the PDF (short cell lines) should be
            // discounted — a heading with an intro paragraph + just a table
            // header row is still orphaned.

            // Check if this heading's section contains a table (from Docs API)
            const headingIdx = structuralElements.findIndex(e =>
                e.kind === 'heading' && e.text === matchedHeading.text);
            let sectionHasTable = false;
            if (headingIdx >= 0) {
                for (let si = headingIdx + 1; si < structuralElements.length; si++) {
                    if (structuralElements[si].kind === 'heading') break;
                    if (structuralElements[si].kind === 'table') {
                        sectionHasTable = true;
                        break;
                    }
                }
            }

            let totalContentChars = 0;
            let contentLineCount = 0;
            let hasBulletContent = false;
            for (let k = j + 1; k < lastLines.length; k++) {
                const afterLine = lastLines[k].trim();
                const afterLower = afterLine.toLowerCase();

                // Skip other headings
                if (headingElements.some(h => h.text.toLowerCase() === afterLower)) continue;

                // Bullet content = heading has its own content
                if (/^[●\-•◦▪]/.test(afterLine)) {
                    hasBulletContent = true;
                    break;
                }

                // If this section has a table, don't count short lines
                // (likely table cells) as real body content
                if (sectionHasTable && afterLine.length < 30) continue;

                totalContentChars += afterLine.length;
                contentLineCount++;
            }

            // Orphaned if: no bullets AND either fewer than 3 content lines
            // or fewer than 50 chars of non-heading content
            if (!hasBulletContent && (contentLineCount < 3 || totalContentChars < 50)) {
                return { text: matchedHeading.text, page: pageNum };
            }
        }
    }

    return null;
}

/**
 * Find a heading's startIndex in the document by matching its text content.
 * Returns the startIndex or null if not found.
 */
function findHeadingIndex(doc, headingText) {
    const body = doc.body;
    if (!body || !body.content) return null;

    const normalizedTarget = headingText.trim().toLowerCase();

    for (const element of body.content) {
        if (!element.paragraph) continue;
        const ps = element.paragraph.paragraphStyle;
        if (!ps?.namedStyleType?.startsWith('HEADING')) continue;

        let text = '';
        for (const el of element.paragraph.elements || []) {
            if (el.textRun?.content) text += el.textRun.content;
        }

        if (text.trim().toLowerCase() === normalizedTarget) {
            return element.startIndex;
        }
    }

    // Fallback: check if PDF text is a truncated version of a heading
    // (pdftotext sometimes truncates long lines)
    for (const element of body.content) {
        if (!element.paragraph) continue;
        const ps = element.paragraph.paragraphStyle;
        if (!ps?.namedStyleType?.startsWith('HEADING')) continue;

        let text = '';
        for (const el of element.paragraph.elements || []) {
            if (el.textRun?.content) text += el.textRun.content;
        }

        const normalizedText = text.trim().toLowerCase();
        // Only match if the heading starts with the target text (PDF truncation)
        // and the target is at least 10 chars (avoid short false matches)
        if (normalizedTarget.length >= 10 && normalizedText.startsWith(normalizedTarget)) {
            return element.startIndex;
        }
    }

    return null;
}

module.exports = { init, fixOrphanedHeadings };
