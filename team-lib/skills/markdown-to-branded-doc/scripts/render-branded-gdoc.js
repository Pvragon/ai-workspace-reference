/**
 * Google Docs Renderer (branded-template-v2)
 * @version 1.0.0
 * @date 2026-03-19
 *
 * Maps DocumentIR to a JSON render plan containing proper Google Docs API
 * batchUpdate requests, executable via `gws docs documents batchUpdate`.
 *
 * Reads all styling from a pre-composed branded template — no merge logic,
 * no fallback chains. The template is the single source of truth.
 *
 * Strategy (text-first approach):
 *   1. Build the full plain-text body with newlines, tracking character indices
 *   2. Generate Google Docs API batchUpdate requests referencing those indices
 *   3. Handle tables separately via placeholders
 *
 * The execute-gdoc-api.js script reads the plan and runs it via gws CLI:
 *   gws docs documents create → insertText → batchUpdate (formatting) → tables
 */

const fs = require('fs');
const { spansToPlainText } = require('./lib/parser');

// ============================================================================
// MAIN RENDER FUNCTION
// ============================================================================

/**
 * Render a DocumentIR to a JSON render plan.
 *
 * @param {DocumentIR} ir - Parsed document IR
 * @param {object} template - Pre-composed branded template (branded-template-v2)
 * @param {string} outputPath - Path to write JSON plan
 */
function renderGdoc(ir, template, outputPath) {
    const font = template.documentSettings?.defaultFont || 'Arial';
    const lineSpacing = template.documentSettings?.lineSpacing || 115;

    // Pass 1: Build full plain text and track indices
    const { fullText, segments, tableEntries } = buildTextBody(ir, template);

    // Pass 2: Generate Google Docs API batchUpdate requests from segments
    const requests = buildBatchUpdateRequests(segments, template, fullText.length);

    // Build table data
    const tables = tableEntries.map(t => ({
        placeholder: t.placeholder,
        headers: t.headers,
        rows: t.rows
    }));

    // Extract list item ranges for native bullet application
    const listItems = segments
        .filter(s => s.type === 'list-item')
        .map(s => ({
            startIndex: s.startIndex,
            endIndex: s.endIndex,
            ordered: s.ordered,
            level: s.level
        }));

    // Collect heading indices that need visible page breaks before them
    const pageBreakIndices = segments
        .filter(s => s.type === 'heading' && !s.isTitle && s.text &&
            (/^(appendix|exhibit)\s+[A-Z0-9\-—]/i.test(s.text) ||
             /^schedule\s+[A-Z0-9]{1,3}(\s*[:\-—]|\s*$)/i.test(s.text) ||
             /^signature block\b/i.test(s.text) ||
             /^in witness whereof\b/i.test(s.text)))
        .map(s => ({ index: s.startIndex, text: s.text }));

    const brandName = template.composedFrom?.brand || 'unknown';
    const headerLogo = template.headerFooter?.header?.logo;

    // Header config — support first-page logo vs subsequent-page logo
    const subsequentLogo = template.headerFooter?.header?.subsequentLogo;
    const showOnFirstPage = template.headerFooter?.header?.showOnFirstPage !== false;
    const showOnSubsequentPages = template.headerFooter?.header?.showOnSubsequentPages !== false;

    const plan = {
        version: "2.4",
        renderer: "gws-cli",
        title: ir.title || "Untitled Document",
        brand: brandName,
        templateType: template.composedFrom?.template || 'unknown',
        googleDocTemplates: template.googleDocTemplates || null,
        content: fullText,
        requests,
        listItems,
        tables,
        header_footer: {
            header: brandName,
            footer: template.headerFooter?.footer?.text || "",
            logoPath: headerLogo?.absolutePath || null,
            logoDimensions: headerLogo ? { width: headerLogo.width, height: headerLogo.height } : null,
            subsequentLogoPath: subsequentLogo?.absolutePath || null,
            subsequentLogoDimensions: subsequentLogo ? { width: subsequentLogo.width, height: subsequentLogo.height } : null,
            showOnFirstPage,
            showOnSubsequentPages,
            pageNumbers: template.headerFooter?.footer?.pageNumbers !== false,
            pageNumberAlignment: template.headerFooter?.footer?.pageNumberAlignment || "right"
        },
        documentSettings: {
            pageMode: template.documentSettings?.pageMode || "PAGED",
            lineSpacing,
            defaultFontSize: template.documentSettings?.defaultFontSize || 11,
            defaultFont: font
        },
        pageBreaks: {
            orphanDetection: template.pageBreaks?.orphanDetection !== false,
            indices: pageBreakIndices
        },
        tableStyle: template.tables || null
    };

    fs.writeFileSync(outputPath, JSON.stringify(plan, null, 2));
    console.log(`Successfully generated render plan: ${outputPath}`);
    console.log(`Brand: ${brandName}`);
    console.log(`batchUpdate requests: ${requests.length}`);
    console.log(`Tables: ${tables.length}`);
}

// ============================================================================
// HELPERS: HEX COLOR TO GOOGLE DOCS RGBCOLOR
// ============================================================================

/**
 * Convert a hex color (e.g., "1E4958" or "#1E4958") to Google Docs rgbColor object.
 */
function hexToRgb(hex) {
    hex = hex.replace(/^#/, '');
    return {
        red: parseInt(hex.substring(0, 2), 16) / 255,
        green: parseInt(hex.substring(2, 4), 16) / 255,
        blue: parseInt(hex.substring(4, 6), 16) / 255
    };
}

// ============================================================================
// PASS 1: TEXT BODY BUILDER
// ============================================================================

/**
 * Build the full plain text content and track segments with their positions.
 * Google Docs uses 1-based indexing where index 1 is before the first character.
 *
 * Each segment records: { startIndex, endIndex, type, ...metadata }
 */
function buildTextBody(ir, template) {
    const parts = [];
    const segments = [];
    const tableEntries = [];
    let tableCounter = 0;
    let offset = 1; // Google Docs 1-based index
    let seenFirstSubtitle = false;
    const subtitleDetection = template.renderOptions?.subtitleDetection === true;
    const isLetterhead = template.renderOptions?.letterheadMode === true;
    let letterheadZone = isLetterhead ? 'address' : null; // 'address' | 'body' | 'signature' | null

    // HR character from template
    const hrChar = template.horizontalRule?.character || '—';
    const hrRepeat = template.horizontalRule?.repeatCount || 32;
    const hrText = hrChar.repeat(hrRepeat);

    for (const block of ir.blocks) {
        switch (block.type) {
            case 'heading': {
                // Letterhead: skip the title heading — the template header
                // handles branding. The title still sets the doc name via ir.title.
                if (isLetterhead && block.isTitle) break;

                const text = block.text;
                const startIndex = offset;
                parts.push(text + '\n');
                offset += text.length + 1;

                segments.push({
                    type: 'heading',
                    startIndex,
                    endIndex: startIndex + text.length,
                    effectiveLevel: block.effectiveLevel,
                    isTitle: block.isTitle,
                    text: text
                });
                break;
            }

            case 'paragraph': {
                const plainText = spansToPlainText(block.spans);
                if (!plainText.trim()) {
                    parts.push('\n');
                    offset += 1;
                    break;
                }

                const startIndex = offset;
                parts.push(plainText + '\n');

                let spanOffset = startIndex;
                for (const span of block.spans) {
                    const len = span.text.length;
                    if (len > 0) {
                        segments.push({
                            type: 'span',
                            spanType: span.type,
                            startIndex: spanOffset,
                            endIndex: spanOffset + len,
                            text: span.text,
                            isLabel: span.isLabel,
                            href: span.href,
                            internal: span.internal,
                            variant: block.variant
                        });
                    }
                    spanOffset += len;
                }

                // Letterhead zone detection — track transitions for spacing
                let isGreeting = false;
                let isClosing = false;
                if (isLetterhead && letterheadZone === 'address') {
                    if (/^(dear |to whom|attention)/i.test(plainText.trim())) {
                        letterheadZone = 'body';
                        isGreeting = true;
                    }
                }
                if (isLetterhead && letterheadZone === 'body') {
                    // Match closing salutations — must be short standalone lines,
                    // not the start of a sentence like "Thank you for..."
                    const trimmed = plainText.trim();
                    if (/^(sincerely|regards|respectfully|warm regards|cordially|best regards|kind regards|yours truly|yours faithfully),?\s*$/i.test(trimmed) ||
                        /^thank you,?\s*$/i.test(trimmed) ||
                        /^best,?\s*$/i.test(trimmed)) {
                        letterheadZone = 'signature';
                        isClosing = true;
                    }
                }

                // When subtitleDetection is off, treat subtitle variants as normal paragraphs
                const effectiveVariant = subtitleDetection ? block.variant :
                    (block.variant === 'subtitle' || block.variant === 'centered-subtitle' || block.variant === 'date-subtitle')
                        ? 'normal' : block.variant;

                let isFirstSubtitle = false;
                if (effectiveVariant === 'subtitle' && !seenFirstSubtitle) {
                    isFirstSubtitle = true;
                    seenFirstSubtitle = true;
                }

                segments.push({
                    type: 'paragraph',
                    startIndex,
                    endIndex: startIndex + plainText.length + 1,
                    variant: effectiveVariant,
                    isFirstSubtitle,
                    letterheadZone: isLetterhead ? letterheadZone : undefined,
                    isGreeting: isGreeting || undefined,
                    isClosing: isClosing || undefined
                });

                offset += plainText.length + 1;
                break;
            }

            case 'list': {
                renderListText(block, parts, segments, offset, (newOffset) => { offset = newOffset; });
                break;
            }

            case 'table': {
                tableCounter++;
                const placeholder = `[TABLE_${tableCounter}]`;
                const startIndex = offset;
                parts.push(placeholder + '\n');
                offset += placeholder.length + 1;

                segments.push({
                    type: 'table-placeholder',
                    startIndex,
                    endIndex: startIndex + placeholder.length,
                    tableIndex: tableCounter - 1
                });

                tableEntries.push({
                    placeholder,
                    headers: block.headers,
                    rows: block.rows
                });
                break;
            }

            case 'metadata-table': {
                tableCounter++;
                const placeholder = `[TABLE_${tableCounter}]`;
                const startIndex = offset;
                parts.push(placeholder + '\n');
                offset += placeholder.length + 1;

                segments.push({
                    type: 'table-placeholder',
                    startIndex,
                    endIndex: startIndex + placeholder.length,
                    tableIndex: tableCounter - 1
                });

                tableEntries.push({
                    placeholder,
                    headers: ['Field', 'Value'],
                    rows: block.entries.map(e => [e.label, e.value])
                });
                break;
            }

            case 'hr': {
                const startIndex = offset;
                parts.push(hrText + '\n');
                offset += hrText.length + 1;

                segments.push({
                    type: 'hr',
                    startIndex,
                    endIndex: startIndex + hrText.length
                });
                break;
            }

            case 'spacer': {
                parts.push('\n');
                offset += 1;
                break;
            }
        }
    }

    return {
        fullText: parts.join(''),
        segments,
        tableEntries
    };
}

/**
 * Recursively render list items into text and track segments.
 * Outputs plain text only (no prefix/indent) — native bullets are applied
 * via createParagraphBullets in the executor.
 */
function renderListText(block, parts, segments, offset, setOffset) {
    const isOrdered = block.ordered;

    block.items.forEach((item, index) => {
        const plainText = spansToPlainText(item.spans);
        const startIndex = offset;

        parts.push(plainText + '\n');
        offset += plainText.length + 1;

        segments.push({
            type: 'list-item',
            startIndex,
            endIndex: startIndex + plainText.length + 1,
            ordered: isOrdered,
            level: block.level,
            itemIndex: index
        });

        let spanOffset = startIndex;
        for (const span of item.spans) {
            const len = span.text.length;
            if (len > 0) {
                segments.push({
                    type: 'span',
                    spanType: span.type,
                    startIndex: spanOffset,
                    endIndex: spanOffset + len,
                    text: span.text,
                    isLabel: span.isLabel,
                    href: span.href,
                    internal: span.internal
                });
            }
            spanOffset += len;
        }

        setOffset(offset);

        for (const subList of item.subLists) {
            renderListText(subList, parts, segments, offset, (newOffset) => {
                offset = newOffset;
                setOffset(offset);
            });
        }
    });
}

// ============================================================================
// PASS 2: GOOGLE DOCS API BATCHUPDATE REQUESTS
// ============================================================================

/**
 * Generate Google Docs API batchUpdate request objects from tracked segments.
 * All styling values come from the pre-composed branded template.
 */
function buildBatchUpdateRequests(segments, template, contentLength) {
    const requests = [];
    const font = template.documentSettings?.defaultFont || 'Arial';
    const fontSize = template.documentSettings?.defaultFontSize || 12;
    const lineSpacing = template.documentSettings?.lineSpacing || 115;

    // Base text style for entire document
    const endIndex = contentLength + 1; // +1 for the 1-based index offset
    requests.push({
        updateTextStyle: {
            range: { startIndex: 1, endIndex },
            textStyle: {
                fontSize: { magnitude: fontSize, unit: "PT" },
                weightedFontFamily: { fontFamily: font }
            },
            fields: "fontSize,weightedFontFamily"
        }
    });

    // Base line spacing for entire document
    requests.push({
        updateParagraphStyle: {
            range: { startIndex: 1, endIndex },
            paragraphStyle: {
                lineSpacing: lineSpacing
            },
            fields: "lineSpacing"
        }
    });

    for (let i = 0; i < segments.length; i++) {
        const seg = segments[i];
        // Look ahead to determine if this is the last list item before a non-list segment
        const nextNonSpan = segments.slice(i + 1).find(s => s.type !== 'span');
        const isLastInList = seg.type === 'list-item' && (!nextNonSpan || nextNonSpan.type !== 'list-item');

        switch (seg.type) {
            case 'heading':
                requests.push(...buildHeadingRequests(seg, template));
                break;

            case 'paragraph':
                requests.push(...buildParagraphRequests(seg, template));
                break;

            case 'span':
                requests.push(...buildSpanRequests(seg, template));
                break;

            case 'list-item':
                requests.push(...buildListItemRequests(seg, template, isLastInList));
                break;

            case 'hr': {
                const hrStyle = template.horizontalRule || {};
                requests.push({
                    updateTextStyle: {
                        range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                        textStyle: {
                            fontSize: { magnitude: hrStyle.fontSize || 8, unit: "PT" },
                            foregroundColor: { color: { rgbColor: hexToRgb(hrStyle.color || '999999') } }
                        },
                        fields: "fontSize,foregroundColor"
                    }
                });
                break;
            }
        }
    }

    return requests;
}

/**
 * Build heading formatting requests from template heading definitions.
 * Supports h1–h6 plus title from template.titleBlock.
 */
function buildHeadingRequests(seg, template) {
    const requests = [];
    const font = template.documentSettings?.defaultFont || 'Arial';

    // Get heading style from template
    let style;
    if (seg.effectiveLevel === 'title' || seg.isTitle) {
        const t = template.titleBlock?.title || {};
        style = {
            namedStyle: t.namedStyle || 'HEADING_1',
            fontSize: t.fontSize || 26,
            color: t.color || template.headings?.h1?.color || '000000',
            font: t.font || font,
            bold: t.bold !== false,
            spaceBefore: t.spaceBefore || 0,
            spaceAfter: t.spaceAfter || 6,
            keepWithNext: t.keepWithNext || false
        };
    } else {
        const h = template.headings?.[seg.effectiveLevel] || {};
        style = {
            namedStyle: h.namedStyle || 'HEADING_3',
            fontSize: h.fontSize || 12,
            color: h.color || '000000',
            font: h.font || font,
            bold: h.bold !== false,
            spaceBefore: h.spaceBefore || 12,
            spaceAfter: h.spaceAfter || 3,
            keepWithNext: h.keepWithNext !== false
        };
    }

    // Apply heading paragraph style with spacing
    const paragraphStyle = {
        namedStyleType: style.namedStyle,
        spaceAbove: { magnitude: style.spaceBefore, unit: "PT" },
        spaceBelow: { magnitude: style.spaceAfter, unit: "PT" }
    };
    let fields = "namedStyleType,spaceAbove,spaceBelow";

    if (style.keepWithNext) {
        paragraphStyle.keepWithNext = true;
        fields += ",keepWithNext";
    }

    requests.push({
        updateParagraphStyle: {
            range: { startIndex: seg.startIndex, endIndex: seg.endIndex + 1 },
            paragraphStyle,
            fields
        }
    });

    // Apply text formatting
    const textStyle = {
        bold: style.bold,
        fontSize: { magnitude: style.fontSize, unit: "PT" },
        weightedFontFamily: { fontFamily: style.font },
        foregroundColor: { color: { rgbColor: hexToRgb(style.color) } }
    };
    let textFields = "bold,fontSize,weightedFontFamily,foregroundColor";

    if (style.italic) {
        textStyle.italic = true;
        textFields += ",italic";
    }

    requests.push({
        updateTextStyle: {
            range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
            textStyle,
            fields: textFields
        }
    });

    return requests;
}

/**
 * Build paragraph formatting requests using template body text and title block styles.
 */
function buildParagraphRequests(seg, template) {
    const requests = [];
    const font = template.documentSettings?.defaultFont || 'Arial';
    const bodyText = template.bodyText?.normal || {};

    // Letterhead: greeting line — 12pt space above to separate from address block
    if (seg.isGreeting) {
        const greetingStyle = template.bodyText?.greeting || {};
        requests.push({
            updateParagraphStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                paragraphStyle: {
                    spaceAbove: { magnitude: greetingStyle.spaceBefore || 12, unit: "PT" },
                    spaceBelow: { magnitude: greetingStyle.spaceAfter || 6, unit: "PT" }
                },
                fields: "spaceAbove,spaceBelow"
            }
        });
        return requests;
    }

    // Letterhead: closing line ("Sincerely,") — 12pt above, 24pt below for signature room
    if (seg.isClosing) {
        const closingStyle = template.bodyText?.closing || {};
        requests.push({
            updateParagraphStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                paragraphStyle: {
                    spaceAbove: { magnitude: closingStyle.spaceBefore || 12, unit: "PT" },
                    spaceBelow: { magnitude: closingStyle.spaceAfter || 24, unit: "PT" }
                },
                fields: "spaceAbove,spaceBelow"
            }
        });
        return requests;
    }

    // Letterhead address block — dense, single-spaced, slightly smaller font
    if (seg.letterheadZone === 'address') {
        const bodyFontSize = template.documentSettings?.defaultFontSize || 11;
        requests.push({
            updateParagraphStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                paragraphStyle: {
                    spaceAbove: { magnitude: 0, unit: "PT" },
                    spaceBelow: { magnitude: 0, unit: "PT" },
                    lineSpacing: 115
                },
                fields: "spaceAbove,spaceBelow,lineSpacing"
            }
        });
        requests.push({
            updateTextStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex - 1 },
                textStyle: {
                    fontSize: { magnitude: bodyFontSize - 1, unit: "PT" }
                },
                fields: "fontSize"
            }
        });
        return requests;
    }

    // Letterhead signature block — dense, single-spaced
    if (seg.letterheadZone === 'signature') {
        requests.push({
            updateParagraphStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                paragraphStyle: {
                    spaceAbove: { magnitude: 0, unit: "PT" },
                    spaceBelow: { magnitude: 0, unit: "PT" },
                    lineSpacing: 115
                },
                fields: "spaceAbove,spaceBelow,lineSpacing"
            }
        });
        return requests;
    }

    // Normal paragraphs — spacing from template
    if (!seg.variant || seg.variant === 'normal') {
        requests.push({
            updateParagraphStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                paragraphStyle: {
                    spaceAbove: { magnitude: bodyText.spaceBefore || 6, unit: "PT" },
                    spaceBelow: { magnitude: bodyText.spaceAfter || 0, unit: "PT" }
                },
                fields: "spaceAbove,spaceBelow"
            }
        });
    }

    if (seg.variant === 'subtitle' && seg.isFirstSubtitle) {
        // First subtitle line gets the SUBTITLE named style
        const subtitleStyle = template.titleBlock?.subtitle || {};
        requests.push({
            updateParagraphStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                paragraphStyle: {
                    namedStyleType: subtitleStyle.namedStyle || "SUBTITLE",
                    spaceAbove: { magnitude: subtitleStyle.spaceBefore || 0, unit: "PT" },
                    spaceBelow: { magnitude: subtitleStyle.spaceAfter || 6, unit: "PT" }
                },
                fields: "namedStyleType,spaceAbove,spaceBelow"
            }
        });
    } else if (seg.variant === 'subtitle') {
        // Metadata lines (Date, Prepared for, etc.)
        const metaStyle = template.titleBlock?.metadataValue || {};
        requests.push({
            updateTextStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex - 1 },
                textStyle: {
                    fontSize: { magnitude: metaStyle.fontSize || 10, unit: "PT" },
                    weightedFontFamily: { fontFamily: metaStyle.font || font }
                },
                fields: "fontSize,weightedFontFamily"
            }
        });
    } else if (seg.variant === 'centered-subtitle') {
        requests.push({
            updateParagraphStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                paragraphStyle: { alignment: "CENTER" },
                fields: "alignment"
            }
        });
    } else if (seg.variant === 'date-subtitle') {
        requests.push({
            updateParagraphStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                paragraphStyle: { alignment: "CENTER" },
                fields: "alignment"
            }
        });
        // Use subtle/muted color from theme
        const subtleColor = template.themeColors?.accent3 || template.horizontalRule?.color || '999999';
        requests.push({
            updateTextStyle: {
                range: { startIndex: seg.startIndex, endIndex: seg.endIndex - 1 },
                textStyle: {
                    italic: true,
                    foregroundColor: { color: { rgbColor: hexToRgb(subtleColor) } }
                },
                fields: "italic,foregroundColor"
            }
        });
    }

    return requests;
}

/**
 * Build span-level formatting requests using template inline styles.
 */
function buildSpanRequests(seg, template) {
    const requests = [];
    const inlineStyles = template.inlineStyles || {};

    switch (seg.spanType) {
        case 'bold': {
            const labelColor = inlineStyles.boldLabel?.color;
            const useLabel = seg.isLabel && labelColor;
            requests.push({
                updateTextStyle: {
                    range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                    textStyle: {
                        bold: true,
                        ...(useLabel ? { foregroundColor: { color: { rgbColor: hexToRgb(labelColor) } } } : {})
                    },
                    fields: useLabel ? "bold,foregroundColor" : "bold"
                }
            });
            break;
        }

        case 'italic':
            requests.push({
                updateTextStyle: {
                    range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                    textStyle: { italic: true },
                    fields: "italic"
                }
            });
            break;

        case 'code': {
            const codeFont = inlineStyles.code?.font || 'Courier New';
            requests.push({
                updateTextStyle: {
                    range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                    textStyle: { weightedFontFamily: { fontFamily: codeFont } },
                    fields: "weightedFontFamily"
                }
            });
            break;
        }

        case 'link': {
            if (!seg.internal && seg.href) {
                const linkColor = inlineStyles.link?.color || '0563C1';
                requests.push({
                    updateTextStyle: {
                        range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
                        textStyle: {
                            link: { url: seg.href },
                            foregroundColor: { color: { rgbColor: hexToRgb(linkColor) } },
                            underline: true
                        },
                        fields: "link,foregroundColor,underline"
                    }
                });
            }
            break;
        }
    }

    return requests;
}

/**
 * Build list item formatting requests using template list spacing.
 */
function buildListItemRequests(seg, template, isLastInList) {
    const requests = [];
    const lists = template.lists || {};
    const spacing = lists.spacing || {};

    // Spacing from template list config
    const levelKey = `level${Math.min(seg.level, 2)}`;
    const levelSpacing = spacing[levelKey] || {};
    const spaceAbove = levelSpacing.spaceBefore || (seg.level === 0 ? 6 : seg.level === 1 ? 3 : 1);
    const lastItemSpace = lists.lastItemSpaceAfter || 6;
    const spaceBelow = isLastInList ? lastItemSpace : (levelSpacing.spaceAfter || 0);

    requests.push({
        updateParagraphStyle: {
            range: { startIndex: seg.startIndex, endIndex: seg.endIndex },
            paragraphStyle: {
                spaceAbove: { magnitude: spaceAbove, unit: "PT" },
                spaceBelow: { magnitude: spaceBelow, unit: "PT" }
            },
            fields: "spaceAbove,spaceBelow"
        }
    });

    return requests;
}

module.exports = { renderGdoc };
