/**
 * DOCX Renderer (branded-template-v2)
 * @version 1.0.0
 * @date 2026-03-19
 *
 * Maps DocumentIR blocks/spans to docx library objects.
 * Reads all styling from a pre-composed branded template — no merge logic,
 * no fallback chains. The template is the single source of truth.
 */

const fs = require('fs');
const path = require('path');
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, Header, Footer,
    AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType, VerticalAlign,
    PageNumber, ImageRun, LevelFormat, ExternalHyperlink, InternalHyperlink,
    BookmarkStart, BookmarkEnd } = require('docx');
const { imageSize: sizeOf } = require('image-size');

let bookmarkIdCounter = 1;

// ============================================================================
// MAIN RENDER FUNCTION
// ============================================================================

/**
 * Render a DocumentIR to a .docx file.
 *
 * @param {DocumentIR} ir - Parsed document IR
 * @param {object} template - Pre-composed branded template (branded-template-v2)
 * @param {string} outputPath - Path to write .docx
 */
async function renderDocx(ir, template, outputPath) {
    const font = template.documentSettings?.defaultFont || 'Arial';
    const lineSpacingPct = template.documentSettings?.lineSpacing || 115;
    const LINE_SPACING = Math.round(240 * (lineSpacingPct / 100)); // Convert percentage to docx twips

    // Reset bookmark counter per render
    bookmarkIdCounter = 1;

    const elements = [];

    for (const block of ir.blocks) {
        switch (block.type) {
            case 'heading':
                elements.push(renderHeading(block, template, LINE_SPACING));
                break;

            case 'paragraph':
                elements.push(renderParagraph(block, template, LINE_SPACING));
                break;

            case 'list':
                elements.push(...renderList(block, template, LINE_SPACING));
                break;

            case 'table':
                elements.push(renderTable(block, template));
                elements.push(new Paragraph({ text: "", spacing: { after: 120 } }));
                break;

            case 'metadata-table':
                elements.push(renderMetadataTable(block, template));
                break;

            case 'hr':
                elements.push(renderHorizontalRule(template));
                break;

            case 'spacer':
                elements.push(new Paragraph({ text: "", spacing: { after: block.after } }));
                break;
        }
    }

    const doc = createDocument(elements, template, ir.metadata, ir.orderedListCount, LINE_SPACING);

    const buffer = await Packer.toBuffer(doc);
    fs.writeFileSync(outputPath, buffer);
    console.log(`Successfully generated ${outputPath}`);
    console.log(`Brand: ${template.composedFrom?.brand || 'unknown'}`);
}

// ============================================================================
// BLOCK RENDERERS
// ============================================================================

function renderHeading(block, template, LINE_SPACING) {
    const bid = bookmarkIdCounter++;

    let headingLevel;
    const config = {
        spacing: { before: 0, line: LINE_SPACING },
        keepNext: true,
        keepLines: true
    };

    // Get heading style from template
    if (block.effectiveLevel === 'title' || block.isTitle) {
        headingLevel = HeadingLevel.TITLE;
        const t = template.titleBlock?.title || {};
        config.alignment = AlignmentType.LEFT;
        const sBeforeTwips = (t.spaceBefore || 12) * 20;
        const sAfterTwips = (t.spaceAfter || 12) * 20;
        config.spacing = { before: sBeforeTwips, after: sAfterTwips, line: LINE_SPACING };
    } else {
        const h = template.headings?.[block.effectiveLevel] || {};
        const levelMap = {
            'h1': HeadingLevel.HEADING_1,
            'h2': HeadingLevel.HEADING_2,
            'h3': HeadingLevel.HEADING_3,
            'h4': HeadingLevel.HEADING_4,
            'h5': HeadingLevel.HEADING_5,
            'h6': HeadingLevel.HEADING_6
        };
        headingLevel = levelMap[block.effectiveLevel] || HeadingLevel.HEADING_3;
        // Convert pt spaceBefore to twips (1pt = 20 twips)
        config.spacing.before = (h.spaceBefore || 12) * 20;

        // Use keepWithNext from template
        if (h.keepWithNext === false) {
            config.keepNext = false;
        }
    }

    config.heading = headingLevel;
    config.children = [
        new BookmarkStart({ id: bid, name: block.anchorId }),
        new TextRun({ text: block.text }),
        new BookmarkEnd({ id: bid })
    ];

    return new Paragraph(config);
}

function renderParagraph(block, template, LINE_SPACING) {
    const text = block.text || '';
    const subtleColor = template.themeColors?.accent3 || template.horizontalRule?.color || '999999';
    const subtitleDetection = template.renderOptions?.subtitleDetection === true;

    // Subtitle variants only apply when subtitleDetection is enabled
    if (subtitleDetection) {
        // Centered subtitle (party names like "Name × Name")
        if (block.variant === 'centered-subtitle') {
            return new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 60, line: LINE_SPACING },
                children: renderSpans(block.spans, template)
            });
        }

        // Date/italic subtitle
        if (block.variant === 'date-subtitle') {
            const emText = block.spans.length > 0 ? block.spans[0].text : '';
            return new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 240, line: LINE_SPACING },
                children: [new TextRun({ text: emText, italics: true, color: subtleColor })]
            });
        }

        // Normal subtitle (pre-content, after title)
        if (block.variant === 'subtitle') {
            return new Paragraph({
                style: "Subtitle",
                spacing: { after: 120, line: 240 },
                children: renderSpans(block.spans, template)
            });
        }

        // Check for centered subtitle patterns in normal paragraphs too
        if (text.includes('\u00d7') && text.length < 60) {
            return new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 60, line: LINE_SPACING },
                children: renderSpans(block.spans, template)
            });
        }

        // Check for date/italic pattern in normal paragraphs
        if (block.spans.length === 1 && block.spans[0].type === 'italic') {
            const emText = block.spans[0].text || '';
            if (!emText.toLowerCase().startsWith('example:')) {
                return new Paragraph({
                    alignment: AlignmentType.CENTER,
                    spacing: { after: 240, line: LINE_SPACING },
                    children: [new TextRun({ text: emText, italics: true, color: subtleColor })]
                });
            }
        }
    }

    return new Paragraph({
        spacing: { line: LINE_SPACING },
        children: renderSpans(block.spans, template)
    });
}

function renderList(block, template, LINE_SPACING) {
    const paragraphs = [];
    const ref = block.listId;

    block.items.forEach((item, index) => {
        const spacing = { before: 120, line: LINE_SPACING };
        if (item.isLast) {
            spacing.after = 240;
        }

        paragraphs.push(new Paragraph({
            numbering: { reference: ref, level: block.level },
            spacing,
            children: renderSpans(item.spans, template)
        }));

        // Recursively render sublists
        item.subLists.forEach(subList => {
            paragraphs.push(...renderList(subList, template, LINE_SPACING));
        });
    });

    return paragraphs;
}

function renderTable(block, template) {
    const headerCells = block.headers;
    const dataRows = block.rows;
    const tableConfig = template.tables || {};

    // Calculate column widths
    const totalWidth = 9360;
    const minColWidth = 1000;

    const colMaxLengths = headerCells.map((header, colIdx) => {
        let maxLen = header.length;
        dataRows.forEach(row => {
            if (row[colIdx]) {
                maxLen = Math.max(maxLen, row[colIdx].length);
            }
        });
        return maxLen;
    });

    const totalContentLength = colMaxLengths.reduce((a, b) => a + b, 0) || 1;

    let columnWidths = colMaxLengths.map(len => {
        const proportionalWidth = Math.floor((len / totalContentLength) * totalWidth);
        return Math.max(proportionalWidth, minColWidth);
    });

    const currentTotal = columnWidths.reduce((a, b) => a + b, 0);
    const diff = totalWidth - currentTotal;
    if (diff !== 0 && columnWidths.length > 0) {
        const maxIdx = columnWidths.indexOf(Math.max(...columnWidths));
        columnWidths[maxIdx] += diff;
    }

    const borderColor = tableConfig.borders?.color || 'CCCCCC';
    const tableBorder = { style: BorderStyle.SINGLE, size: 1, color: borderColor };
    const tableRows = [];

    const getContrastColor = (hex) => {
        if (!hex) return "000000";
        const r = parseInt(hex.substr(0, 2), 16);
        const g = parseInt(hex.substr(2, 2), 16);
        const b = parseInt(hex.substr(4, 2), 16);
        const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
        return (yiq >= 128) ? "000000" : "FFFFFF";
    };

    // Header row styling from template
    const headerBg = tableConfig.headerRow?.background || '333333';
    const headerTextColor = tableConfig.headerRow?.fontColor || getContrastColor(headerBg);

    // Header row
    tableRows.push(new TableRow({
        tableHeader: true,
        children: headerCells.map((cell, idx) => new TableCell({
            borders: { top: tableBorder, bottom: tableBorder, left: tableBorder, right: tableBorder },
            width: { size: columnWidths[idx], type: WidthType.DXA },
            shading: { fill: headerBg, type: ShadingType.CLEAR },
            verticalAlign: VerticalAlign.CENTER,
            children: [new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({ text: cell, bold: true, color: headerTextColor })]
            })]
        }))
    }));

    // Data rows with alternating backgrounds from template
    const bodyBg = tableConfig.bodyRow?.background || 'FFFFFF';
    const altBg = tableConfig.alternateRowBackground || bodyBg;

    dataRows.forEach((row, idx) => {
        tableRows.push(new TableRow({
            children: row.map((cell, colIdx) => new TableCell({
                borders: { top: tableBorder, bottom: tableBorder, left: tableBorder, right: tableBorder },
                width: { size: columnWidths[colIdx] || columnWidths[0], type: WidthType.DXA },
                shading: { fill: idx % 2 === 0 ? altBg : bodyBg, type: ShadingType.CLEAR },
                children: [new Paragraph({
                    children: renderInlineText(cell, template)
                })]
            }))
        }));
    });

    return new Table({
        columnWidths,
        margins: { top: 100, bottom: 100, left: 180, right: 180 },
        rows: tableRows
    });
}

function renderMetadataTable(block, template) {
    const tableConfig = template.tables || {};
    const borderColor = tableConfig.borders?.color || 'CCCCCC';
    const tableBorder = { style: BorderStyle.SINGLE, size: 1, color: borderColor };

    const labelBg = tableConfig.alternateRowBackground || 'F0F0F0';
    const valueBg = tableConfig.bodyRow?.background || 'FFFFFF';
    const labelColor = template.themeColors?.dark2 || '333333';

    const tableRows = block.entries.map(entry =>
        new TableRow({
            children: [
                new TableCell({
                    borders: { top: tableBorder, bottom: tableBorder, left: tableBorder, right: tableBorder },
                    width: { size: 3000, type: WidthType.DXA },
                    shading: { fill: labelBg, type: ShadingType.CLEAR },
                    children: [new Paragraph({
                        children: [new TextRun({ text: entry.label, bold: true, color: labelColor })]
                    })]
                }),
                new TableCell({
                    borders: { top: tableBorder, bottom: tableBorder, left: tableBorder, right: tableBorder },
                    width: { size: 6360, type: WidthType.DXA },
                    shading: { fill: valueBg, type: ShadingType.CLEAR },
                    children: [new Paragraph({
                        children: [new TextRun({ text: entry.value })]
                    })]
                })
            ]
        })
    );

    return new Table({
        width: { size: 9360, type: WidthType.DXA },
        rows: tableRows,
        margins: { top: 100, bottom: 100, left: 180, right: 180 }
    });
}

function renderHorizontalRule(template) {
    const hrColor = template.horizontalRule?.color || '999999';
    return new Paragraph({
        spacing: { before: 200, after: 80 },
        border: {
            bottom: { color: hrColor, style: BorderStyle.SINGLE, size: 12, space: 1 }
        },
        children: []
    });
}

// ============================================================================
// SPAN RENDERERS
// ============================================================================

/**
 * Convert IR spans to docx TextRun/Hyperlink objects.
 */
function renderSpans(spans, template) {
    const runs = [];
    const inlineStyles = template.inlineStyles || {};
    const labelColor = inlineStyles.boldLabel?.color;
    const linkColor = inlineStyles.link?.color || '0563C1';

    for (const span of spans) {
        switch (span.type) {
            case 'text':
                runs.push(new TextRun(span.text));
                break;

            case 'bold':
                if (span.isLabel && labelColor) {
                    runs.push(new TextRun({ text: span.text, bold: true, color: labelColor }));
                } else {
                    runs.push(new TextRun({ text: span.text, bold: true }));
                }
                break;

            case 'italic':
                runs.push(new TextRun({ text: span.text, italics: true }));
                break;

            case 'code': {
                const codeFont = inlineStyles.code?.font || 'Courier New';
                runs.push(new TextRun({ text: span.text, font: codeFont }));
                break;
            }

            case 'link':
                if (span.internal) {
                    runs.push(new InternalHyperlink({
                        children: [new TextRun({ text: span.text, style: "Hyperlink", color: linkColor, underline: true })],
                        anchor: span.anchorId
                    }));
                } else {
                    runs.push(new ExternalHyperlink({
                        children: [new TextRun({ text: span.text, style: "Hyperlink", color: linkColor, underline: true })],
                        link: span.href
                    }));
                }
                break;
        }
    }

    return runs;
}

/**
 * Render plain text with inline formatting detection (for table cells).
 */
function renderInlineText(text, template) {
    const runs = [];
    const inlineStyles = template.inlineStyles || {};
    const labelColor = inlineStyles.boldLabel?.color;
    const linkColor = inlineStyles.link?.color || '0563C1';
    const codeFont = inlineStyles.code?.font || 'Courier New';
    const regex = /\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[([^\]]+)\]\(([^)]+)\)|([^*`\[]+)/g;
    let match;

    while ((match = regex.exec(text)) !== null) {
        if (match[1]) {
            const boldText = match[1];
            if (boldText.trim().endsWith(':') && labelColor) {
                runs.push(new TextRun({ text: boldText, bold: true, color: labelColor }));
            } else {
                runs.push(new TextRun({ text: boldText, bold: true }));
            }
        } else if (match[2]) {
            runs.push(new TextRun({ text: match[2], italics: true }));
        } else if (match[3]) {
            runs.push(new TextRun({ text: match[3], font: codeFont }));
        } else if (match[4] && match[5]) {
            const linkHref = match[5];
            if (linkHref.startsWith('#')) {
                const { generateAnchorId } = require('./lib/parser');
                runs.push(new InternalHyperlink({
                    children: [new TextRun({ text: match[4], style: "Hyperlink", color: linkColor, underline: true })],
                    anchor: generateAnchorId(linkHref.substring(1))
                }));
            } else {
                runs.push(new ExternalHyperlink({
                    children: [new TextRun({ text: match[4], style: "Hyperlink", color: linkColor, underline: true })],
                    link: linkHref
                }));
            }
        } else if (match[6]) {
            runs.push(new TextRun(match[6]));
        }
    }

    return runs.length > 0 ? runs : [new TextRun(text)];
}

// ============================================================================
// DOCUMENT CREATION
// ============================================================================

function createDocument(elements, template, metadata, orderedListCount = 0, LINE_SPACING) {
    const font = template.documentSettings?.defaultFont || 'Arial';
    const brandName = template.composedFrom?.brand || 'unknown';

    // Heading styles from template — map to docx sizes (half-points: 1pt = 2 half-points)
    const h1 = template.headings?.h1 || {};
    const h2 = template.headings?.h2 || {};
    const h3 = template.headings?.h3 || {};
    const h4 = template.headings?.h4 || {};
    const titleStyle = template.titleBlock?.title || {};
    const subtitleStyle = template.titleBlock?.subtitle || {};
    const bodyColor = template.documentSettings?.defaultTextColor || '000000';

    // Prepare logo from template headerFooter
    let headerChildren = [];
    const logoConfig = template.headerFooter?.header?.logo;
    if (logoConfig?.absolutePath && fs.existsSync(logoConfig.absolutePath)) {
        try {
            const logoData = fs.readFileSync(logoConfig.absolutePath);
            const dimensions = sizeOf(logoData);
            let targetWidth = 180;
            let targetHeight = Math.round(targetWidth * (dimensions.height / dimensions.width));

            const MAX_HEIGHT = 80;
            if (targetHeight > MAX_HEIGHT) {
                targetHeight = MAX_HEIGHT;
                targetWidth = Math.round(targetHeight * (dimensions.width / dimensions.height));
            }

            let imgType = dimensions.type;
            if (imgType === 'jpg') imgType = 'jpeg';

            const logoAlignment = template.headerFooter?.header?.logoAlignment === 'left'
                ? AlignmentType.LEFT : AlignmentType.RIGHT;

            headerChildren.push(new Paragraph({
                alignment: logoAlignment,
                children: [
                    new ImageRun({
                        type: imgType,
                        data: logoData,
                        transformation: { width: targetWidth, height: targetHeight },
                        altText: { title: `${brandName} Logo`, description: "Company logo", name: "Logo" }
                    })
                ]
            }));
        } catch (err) {
            console.warn(`Warning: Could not process logo dimensions: ${err.message}. Using fallback.`);
            const fallbackWidth = logoConfig.width || 150;
            const fallbackHeight = logoConfig.height || 50;
            headerChildren.push(new Paragraph({
                alignment: AlignmentType.RIGHT,
                children: [
                    new ImageRun({
                        type: "png",
                        data: fs.readFileSync(logoConfig.absolutePath),
                        transformation: { width: fallbackWidth, height: fallbackHeight },
                        altText: { title: `${brandName} Logo`, description: "Company logo", name: "Logo" }
                    })
                ]
            }));
        }
    }

    const getLevels = (type) => {
        const levels = [];
        for (let i = 0; i < 6; i++) {
            levels.push({
                level: i,
                format: type === 'bullet' ? LevelFormat.BULLET : LevelFormat.DECIMAL,
                text: type === 'bullet' ? (i % 2 === 0 ? "\u2022" : "\u25E6") : "%" + (i + 1) + ".",
                alignment: AlignmentType.LEFT,
                style: {
                    paragraph: {
                        indent: { left: 720 * (i + 1), hanging: 360 },
                        spacing: { before: i === 0 ? 120 : 60, after: 0, line: LINE_SPACING }
                    }
                }
            });
        }
        return levels;
    };

    const numberingConfig = [
        { reference: "bullet-list", levels: getLevels('bullet') },
        { reference: "numbered-list", levels: getLevels('numbered') }
    ];

    for (let i = 1; i <= orderedListCount; i++) {
        numberingConfig.push({
            reference: `numbered-list-${i}`,
            levels: getLevels('numbered')
        });
    }

    // Footer styling from template
    const footerConfig = template.headerFooter?.footer || {};
    const pageNumColor = footerConfig.pageNumberColor || '999999';
    const pageNumSize = (footerConfig.pageNumberFontSize || 9) * 2; // pt to half-points
    const pageNumAlignment = footerConfig.pageNumberAlignment === 'left'
        ? AlignmentType.LEFT
        : footerConfig.pageNumberAlignment === 'center'
            ? AlignmentType.CENTER
            : AlignmentType.RIGHT;

    // Page margins from template (convert pt to twips: 1pt = 20 twips)
    const margins = template.documentSettings?.margins || {};
    const marginTop = (margins.top || 72) * 20;
    const marginBottom = (margins.bottom || 54) * 20;
    const marginLeft = (margins.left || 54) * 20;
    const marginRight = (margins.right || 54) * 20;

    const doc = new Document({
        styles: {
            default: {
                heading1: {
                    run: { size: (h1.fontSize || 14) * 2, bold: h1.bold !== false, color: h1.color || '000000', font: h1.font || font },
                    paragraph: { spacing: { before: (h1.spaceBefore || 18) * 20, after: (h1.spaceAfter || 6) * 20, line: LINE_SPACING } }
                },
                heading2: {
                    run: { size: (h2.fontSize || 14) * 2, bold: h2.bold !== false, color: h2.color || '000000', font: h2.font || font },
                    paragraph: { spacing: { before: (h2.spaceBefore || 14) * 20, after: (h2.spaceAfter || 4) * 20, line: LINE_SPACING } }
                },
                heading3: {
                    run: { size: (h3.fontSize || 12) * 2, bold: h3.bold !== false, color: h3.color || '000000', font: h3.font || font },
                    paragraph: { spacing: { before: (h3.spaceBefore || 12) * 20, after: (h3.spaceAfter || 3) * 20, line: LINE_SPACING } }
                },
                heading4: {
                    run: { size: (h4.fontSize || 11) * 2, bold: h4.bold !== false, color: h4.color || '000000', font: h4.font || font },
                    paragraph: { spacing: { before: (h4.spaceBefore || 10) * 20, after: (h4.spaceAfter || 2) * 20, line: LINE_SPACING } }
                },
                title: {
                    run: { size: (titleStyle.fontSize || 26) * 2, bold: titleStyle.bold !== false, color: titleStyle.color || '000000', font: titleStyle.font || font },
                    paragraph: { alignment: AlignmentType.LEFT, spacing: { before: (titleStyle.spaceBefore || 12) * 20, after: (titleStyle.spaceAfter || 12) * 20, line: LINE_SPACING } }
                }
            },
            paragraphStyles: [
                {
                    id: "Subtitle", name: "Subtitle", basedOn: "Normal", next: "Normal", quickFormat: true,
                    run: { size: (subtitleStyle.fontSize || 14) * 2, bold: subtitleStyle.bold !== false, color: subtitleStyle.color || bodyColor, font: subtitleStyle.font || font },
                    paragraph: { spacing: { before: 0, after: 120, line: LINE_SPACING } }
                },
                {
                    id: "Normal", name: "Normal",
                    run: { size: (template.documentSettings?.defaultFontSize || 12) * 2, color: bodyColor, font },
                    paragraph: { spacing: { line: LINE_SPACING } }
                },
                {
                    id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
                    run: { size: (h1.fontSize || 14) * 2, bold: h1.bold !== false, color: h1.color || '000000', font: h1.font || font },
                    paragraph: { spacing: { before: (h1.spaceBefore || 18) * 20, after: (h1.spaceAfter || 6) * 20, line: LINE_SPACING }, outlineLevel: 0 }
                },
                {
                    id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
                    run: { size: (h2.fontSize || 14) * 2, bold: h2.bold !== false, color: h2.color || '000000', font: h2.font || font },
                    paragraph: { spacing: { before: (h2.spaceBefore || 14) * 20, after: (h2.spaceAfter || 4) * 20, line: LINE_SPACING }, outlineLevel: 1 }
                },
                {
                    id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
                    run: { size: (h3.fontSize || 12) * 2, bold: h3.bold !== false, color: h3.color || '000000', font: h3.font || font },
                    paragraph: { spacing: { before: (h3.spaceBefore || 12) * 20, after: (h3.spaceAfter || 3) * 20, line: LINE_SPACING }, outlineLevel: 2 }
                },
                {
                    id: "Heading4", name: "Heading 4", basedOn: "Normal", next: "Normal", quickFormat: true,
                    run: { size: (h4.fontSize || 11) * 2, bold: h4.bold !== false, color: h4.color || '000000', font: h4.font || font },
                    paragraph: { spacing: { before: (h4.spaceBefore || 10) * 20, after: (h4.spaceAfter || 2) * 20, line: LINE_SPACING }, outlineLevel: 3 }
                }
            ]
        },
        numbering: { config: numberingConfig },
        sections: [{
            properties: {
                page: { margin: { top: marginTop, right: marginRight, bottom: marginBottom, left: marginLeft } }
            },
            headers: headerChildren.length > 0 ? {
                default: new Header({ children: headerChildren })
            } : undefined,
            footers: {
                default: new Footer({
                    children: [
                        new Paragraph({
                            alignment: pageNumAlignment,
                            children: [
                                new TextRun({ children: [PageNumber.CURRENT], size: pageNumSize, color: pageNumColor })
                            ]
                        })
                    ]
                })
            },
            children: elements
        }]
    });

    return doc;
}

module.exports = { renderDocx };
