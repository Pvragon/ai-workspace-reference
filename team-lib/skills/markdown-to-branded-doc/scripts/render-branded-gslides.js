/**
 * Google Slides Renderer (branded-template-v2)
 * @version 0.1.0
 * @date 2026-03-19
 *
 * Converts DocumentIR into a slide plan — an array of slides, each with
 * a layout type and text content for placeholders.
 *
 * Layout selection:
 *   - First heading → title slide (with subtitle if present)
 *   - H1 headings → section divider slides
 *   - H2/H3 with content → content slides
 *   - Tables → content slides with table rendered as formatted text
 *   - Lists → content slides with bullet text
 *
 * This is a template-copy approach: the executor copies a branded slide
 * template and populates layouts. No pixel-level positioning.
 */

const { spansToPlainText } = require('./lib/parser');

/**
 * Render a DocumentIR to a slide plan.
 * @param {Object} ir - DocumentIR from parser
 * @param {Object} template - Composed branded template
 * @param {string} outputPath - Where to write the plan JSON
 */
function renderGslides(ir, template, outputPath) {
    const fs = require('fs');
    const slides = [];
    let currentSlide = null;
    let isFirstHeading = true;

    function flushSlide() {
        if (currentSlide) {
            // Clean up body — trim trailing newlines
            if (currentSlide.body) {
                currentSlide.body = currentSlide.body.trim();
            }
            slides.push(currentSlide);
        }
    }

    for (const block of ir.blocks) {
        switch (block.type) {
            case 'heading': {
                if (block.isTitle || isFirstHeading) {
                    // Title slide
                    flushSlide();
                    currentSlide = {
                        layout: 'title',
                        title: block.text
                    };
                    isFirstHeading = false;
                } else if (block.effectiveLevel === 'h1') {
                    // Major section → section divider or new content slide
                    flushSlide();
                    currentSlide = {
                        layout: 'content',
                        title: block.text,
                        body: ''
                    };
                } else {
                    // H2/H3 → new content slide
                    flushSlide();
                    currentSlide = {
                        layout: 'content',
                        title: block.text,
                        body: ''
                    };
                }
                break;
            }

            case 'paragraph': {
                if (!currentSlide) {
                    // Subtitle for title slide, or pre-content text
                    if (slides.length > 0 && slides[slides.length - 1].layout === 'title') {
                        const plainText = spansToPlainText(block.spans);
                        slides[slides.length - 1].subtitle =
                            (slides[slides.length - 1].subtitle || '') + plainText + '\n';
                    }
                    break;
                }

                const plainText = spansToPlainText(block.spans);
                if (plainText.trim()) {
                    currentSlide.body = (currentSlide.body || '') + plainText + '\n\n';
                }
                break;
            }

            case 'list': {
                if (!currentSlide) break;
                for (const item of (block.items || [])) {
                    const text = spansToPlainText(item.spans);
                    const indent = '  '.repeat(item.level || 0);
                    const bullet = block.ordered ? `${item.index || '•'}. ` : '• ';
                    currentSlide.body = (currentSlide.body || '') + indent + bullet + text + '\n';
                }
                currentSlide.body = (currentSlide.body || '') + '\n';
                break;
            }

            case 'table': {
                flushSlide();
                // Render table as a text-based slide
                const headers = block.headers || [];
                const rows = block.rows || [];
                let tableText = '';

                // Format as aligned text
                if (headers.length > 0) {
                    tableText += headers.join('  |  ') + '\n';
                    tableText += '─'.repeat(60) + '\n';
                }
                for (const row of rows) {
                    tableText += row.join('  |  ') + '\n';
                }

                currentSlide = {
                    layout: 'content',
                    title: 'Data',  // Will be overridden if preceded by heading
                    body: tableText
                };

                // If previous slide was just a heading with no body, merge
                if (slides.length > 0) {
                    const prev = slides[slides.length - 1];
                    if (prev.body === '' || !prev.body) {
                        prev.body = tableText;
                        prev.layout = 'content';
                        currentSlide = null;
                    }
                }
                break;
            }

            case 'hr':
            case 'spacer':
                // Ignore
                break;

            default:
                break;
        }
    }

    flushSlide();

    const plan = {
        version: '0.1',
        renderer: 'gws-slides',
        title: ir.title || 'Untitled Presentation',
        brand: template.composedFrom?.brand || 'unknown',
        templateType: template.composedFrom?.template || 'slides-informational',
        slides
    };

    fs.writeFileSync(outputPath, JSON.stringify(plan, null, 2));
    return plan;
}

module.exports = { renderGslides };
