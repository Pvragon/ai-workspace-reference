/**
 * Markdown Parser → DocumentIR
 * @version 1.0.0
 * @date 2026-03-19
 *
 * Parses markdown into a format-agnostic intermediate representation (IR).
 * The IR is an ordered array of block objects with inline spans, suitable
 * for consumption by any renderer (docx, Google Docs, etc.).
 *
 * Block types: heading, paragraph, list, table, metadata-table, hr, spacer
 * Span types:  text, bold, italic, code, link
 */

const { marked } = require('marked');
const yaml = require('js-yaml');

// ============================================================================
// IR BUILDER
// ============================================================================

/**
 * Parse markdown content into a DocumentIR.
 *
 * @param {string} mdContent - Raw markdown string (may include YAML frontmatter)
 * @param {object} [options] - Parse options
 * @param {boolean} [options.renderMetadataTable=false] - Render YAML frontmatter
 *   as a metadata table block. Default OFF — most agent-authored markdown carries
 *   internal workspace frontmatter (template, version, maintainer, etc.) that should
 *   not appear in the rendered document. Opt in via this flag OR by setting
 *   `_render_metadata_table: true` in the frontmatter itself.
 * @returns {DocumentIR}
 *
 * DocumentIR shape:
 * {
 *   title: string | null,
 *   metadata: object | null,
 *   blocks: Block[]
 * }
 */
function parseMarkdown(mdContent, options = {}) {
    // Extract frontmatter
    let metadata = null;
    const frontmatterRegex = /^---\n([\s\S]*?)\n---/;
    const match = mdContent.match(frontmatterRegex);
    if (match) {
        try {
            metadata = yaml.load(match[1]);
            mdContent = mdContent.replace(frontmatterRegex, '');
        } catch (e) {
            console.warn('Failed to parse frontmatter:', e.message);
        }
    }

    // Metadata-table rendering is OPT-IN. Default off avoids rendering internal
    // workspace bookkeeping (template/version/maintainer/created/last_updated)
    // as a table at the top of the document. Strip the marker field before
    // exposing metadata downstream so it doesn't show up as a row if rendered.
    const optInFromFrontmatter = metadata && metadata._render_metadata_table === true;
    if (metadata && '_render_metadata_table' in metadata) {
        delete metadata._render_metadata_table;
    }
    const renderMetadata = options.renderMetadataTable === true || optInFromFrontmatter;

    const tokens = marked.lexer(mdContent);
    const blocks = [];

    // Document-level state
    let isFirstHeading = true;
    let lastWasHeading1 = false;
    let orderedListsEncountered = 0;
    let reachedContent = false;
    let metadataInserted = false;
    let documentTitle = null;

    // Helper: insert metadata table block at current position
    const tryInsertMetadata = () => {
        if (metadata && renderMetadata && !metadataInserted) {
            blocks.push({ type: 'spacer', after: 120 });
            blocks.push(buildMetadataTable(metadata));
            blocks.push({ type: 'spacer', after: 240 });
            metadataInserted = true;
        }
    };

    for (const token of tokens) {
        // Detect content zone boundary
        if (!reachedContent) {
            if ((token.type === 'heading' && token.depth >= 2) ||
                token.type === 'table' ||
                token.type === 'list' ||
                token.type === 'hr') {
                reachedContent = true;
                tryInsertMetadata();
            }
        }

        // HR before H1/H2 sections (except first)
        if (token.type === 'heading' && token.depth <= 2 && !isFirstHeading && lastWasHeading1) {
            blocks.push({ type: 'hr' });
        }

        switch (token.type) {
            case 'heading': {
                const text = token.text.trim();
                const depth = token.depth;
                const isTitle = isFirstHeading && depth === 1;

                if (isTitle) documentTitle = text;

                let effectiveLevel;
                if (isTitle) {
                    effectiveLevel = 'title';
                } else if (depth === 1 || depth === 2) {
                    effectiveLevel = 'h1';
                } else if (depth === 3) {
                    effectiveLevel = 'h2';
                } else {
                    effectiveLevel = 'h3';
                }

                blocks.push({
                    type: 'heading',
                    depth,
                    text,
                    anchorId: generateAnchorId(text),
                    isTitle,
                    effectiveLevel
                });

                if (depth === 1) isFirstHeading = false;
                lastWasHeading1 = depth <= 2;
                break;
            }

            case 'paragraph': {
                // Standalone image (![alt](src)) → image block
                if (token.tokens && token.tokens.length === 1 && token.tokens[0].type === 'image') {
                    const img = token.tokens[0];
                    reachedContent = true;
                    tryInsertMetadata();
                    blocks.push({ type: 'image', src: img.href, alt: img.text || '' });
                    lastWasHeading1 = false;
                    break;
                }
                if (!reachedContent && !isFirstHeading) {
                    // Pre-content zone (after the H1 title, before the first H2/table/list).
                    // Short lines here are genuine subtitles/date lines; a full intro
                    // PARAGRAPH is body text, not a subtitle. Gate on length so only a
                    // "few words" line takes subtitle styling — otherwise render as normal
                    // body (fixed 2026-07-12: first intro paragraph was rendering in
                    // subtitle font). SUBTITLE_MAX_WORDS is deliberately tight.
                    const SUBTITLE_MAX_WORDS = 12;
                    const lines = token.text.split('\n');
                    lines.forEach(line => {
                        const inlineTokens = marked.lexer(line);
                        const subToken = (inlineTokens[0] && inlineTokens[0].tokens)
                            ? inlineTokens[0] : { text: line, tokens: [] };

                        const spans = parseInlineTokens(subToken.tokens || []);
                        const wordCount = line.trim().split(/\s+/).filter(Boolean).length;
                        // Italic date lines (`*July 12, 2026*`) stay subtitles regardless of
                        // length via classifySubtitle; prose paragraphs fall through to body.
                        const isDateLine = subToken.tokens && subToken.tokens.length === 1
                            && subToken.tokens[0].type === 'em';
                        const variant = (wordCount <= SUBTITLE_MAX_WORDS || isDateLine)
                            ? classifySubtitle(line, subToken.tokens)
                            : 'normal';

                        blocks.push({
                            type: 'paragraph',
                            spans,
                            text: line,
                            variant
                        });
                    });
                } else if (token.text.includes('\n')) {
                    // Multi-line paragraph → split
                    const lines = token.text.split('\n');
                    lines.forEach(line => {
                        const inlineTokens = marked.lexer(line);
                        const subToken = (inlineTokens[0] && inlineTokens[0].tokens)
                            ? inlineTokens[0] : { text: line, tokens: [] };
                        blocks.push({
                            type: 'paragraph',
                            spans: parseInlineTokens(subToken.tokens || []),
                            text: line,
                            variant: 'normal'
                        });
                    });
                } else {
                    blocks.push({
                        type: 'paragraph',
                        spans: parseInlineTokens(token.tokens || []),
                        text: token.text || '',
                        variant: 'normal'
                    });
                }
                lastWasHeading1 = false;
                break;
            }

            case 'list': {
                let listId = undefined;
                if (token.ordered) {
                    orderedListsEncountered++;
                    listId = `numbered-list-${orderedListsEncountered}`;
                }
                blocks.push(buildListBlock(token, listId));
                lastWasHeading1 = false;
                break;
            }

            case 'blockquote': {
                // Render blockquote children (paragraphs / lists) as a callout: tag them
                // `quoted` so the docx renderer can indent them and add a left rule.
                const children = token.tokens || [];
                let first = true;
                for (const child of children) {
                    if (child.type === 'paragraph') {
                        (child.text || '').split('\n').forEach(line => {
                            const it = marked.lexer(line);
                            const sub = (it[0] && it[0].tokens) ? it[0] : { tokens: [] };
                            blocks.push({
                                type: 'paragraph',
                                spans: parseInlineTokens(sub.tokens || []),
                                text: line, variant: 'normal',
                                quoted: true, quotedFirst: first
                            });
                            first = false;
                        });
                    } else if (child.type === 'list') {
                        // Flatten a list inside a blockquote into quoted paragraphs with a
                        // literal marker. Do NOT emit a real list block: its numbering
                        // reference would not be registered, so docx writes an unresolved
                        // <w:numId w:val="{...}"/> placeholder — which is not an integer and
                        // makes Word reject the whole file.
                        let idx = child.ordered ? (child.start || 1) : 0;
                        for (const item of (child.items || [])) {
                            const marker = child.ordered ? `${idx++}. ` : '• ';
                            const itemText = (item.text || '').replace(/\s*\n\s*/g, ' ').trim();
                            const it = marked.lexer(itemText);
                            const sub = (it[0] && it[0].tokens) ? it[0] : { tokens: [] };
                            const spans = [{ type: 'bold', text: marker, isLabel: false },
                                ...parseInlineTokens(sub.tokens || [])];
                            blocks.push({
                                type: 'paragraph',
                                spans,
                                text: marker + itemText, variant: 'normal',
                                quoted: true, quotedFirst: first
                            });
                            first = false;
                        }
                    }
                }
                reachedContent = true;
                lastWasHeading1 = false;
                break;
            }

            case 'table': {
                blocks.push({
                    type: 'table',
                    headers: token.header.map(h => h.text),
                    rows: token.rows.map(row => row.map(cell => cell.text))
                });
                blocks.push({ type: 'spacer', after: 120 });
                lastWasHeading1 = false;
                break;
            }

            case 'hr':
                // Skip explicit HRs — we add them automatically before sections
                break;

            case 'space':
                break;

            default:
                if (token.raw && token.raw.trim()) {
                    console.log(`Unhandled token type: ${token.type}`);
                }
        }
    }

    // Fallback: insert metadata at end if never inserted (gated by renderMetadata)
    if (metadata && renderMetadata && !metadataInserted) {
        tryInsertMetadata();
    }

    // Count total ordered lists for numbering config
    let orderedListCount = 0;
    for (const token of tokens) {
        if (token.type === 'list' && token.ordered) {
            orderedListCount++;
        }
    }

    return {
        title: documentTitle,
        metadata,
        orderedListCount,
        blocks
    };
}

// ============================================================================
// BLOCK BUILDERS
// ============================================================================

function buildMetadataTable(metadata) {
    const entries = Object.entries(metadata).map(([key, value]) => {
        const label = key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase());

        let displayValue = value;
        if (value instanceof Date) {
            displayValue = value.toLocaleDateString();
        } else if (Array.isArray(value)) {
            displayValue = value.join(', ');
        } else if (typeof value === 'object') {
            displayValue = JSON.stringify(value);
        }

        return { key, label, value: String(displayValue) };
    });

    return { type: 'metadata-table', entries };
}

function buildListBlock(token, listId, level = 0) {
    const items = token.items.map((item, index) => {
        const contentTokens = [];
        const subLists = [];

        if (item.tokens) {
            item.tokens.forEach(t => {
                if (t.type === 'list') {
                    subLists.push(t);
                } else {
                    contentTokens.push(t);
                }
            });
        }

        let rawSpans;
        if (contentTokens.length > 0) {
            rawSpans = parseInlineTokens(contentTokens);
        } else if (item.text) {
            rawSpans = parseInlineText(item.text);
        } else {
            rawSpans = [{ type: 'text', text: '' }];
        }

        // Split spans at `\n\n` boundaries (loose-list continuation paragraphs).
        // Markdown allows a list item to have additional indented paragraphs
        // after a blank line; in the IR these come through as text spans
        // containing `\n\n`. If we leave them inside the item, they render as
        // additional bulleted lines (one empty + one with the continuation
        // text). Split them out so the renderer can place them as plain
        // (non-bulleted) paragraphs after any sub-lists.
        const { spans, continuations } = splitSpansAtParagraphBreaks(rawSpans);

        const subListBlocks = subLists.map(sl => buildListBlock(sl, listId, level + 1));
        const isLast = index === token.items.length - 1;

        return { spans, subLists: subListBlocks, continuations, isLast };
    });

    return {
        type: 'list',
        ordered: token.ordered,
        listId: listId || (token.ordered ? 'numbered-list' : 'bullet-list'),
        level,
        items
    };
}

/**
 * Split a span array at `\n\n` text-span boundaries. Returns the primary span
 * group (before the first break) and an array of continuation span groups
 * (one per additional paragraph). Single `\n` inside a text span is collapsed
 * to a space — these are mid-paragraph soft wraps, not paragraph breaks.
 */
function splitSpansAtParagraphBreaks(spans) {
    const primary = [];
    const continuations = [];
    let current = primary;

    for (const span of spans) {
        if (span.type === 'text' && /\n\n/.test(span.text)) {
            const parts = span.text.split(/\n\n+/);
            // Part 0 → current bucket (with single newlines collapsed to spaces)
            const head = parts[0].replace(/\n/g, ' ');
            if (head) current.push({ ...span, text: head });
            for (let i = 1; i < parts.length; i++) {
                current = [];
                continuations.push(current);
                const tail = parts[i].replace(/\n/g, ' ');
                if (tail) current.push({ ...span, text: tail });
            }
        } else if (span.type === 'text' && /\n/.test(span.text)) {
            // Single newlines inside a span are soft wraps — collapse to space
            current.push({ ...span, text: span.text.replace(/\n/g, ' ') });
        } else {
            current.push(span);
        }
    }

    return {
        spans: primary,
        continuations: continuations.map(spanList => ({ spans: spanList }))
    };
}

// ============================================================================
// INLINE PARSING → SPANS
// ============================================================================

/**
 * Classify a pre-content paragraph as a subtitle variant.
 */
function classifySubtitle(text, tokens) {
    if (text.includes('\u00d7') && text.length < 60) {
        return 'centered-subtitle'; // Party names like "Name × Name"
    }
    if (tokens && tokens.length === 1 && tokens[0].type === 'em') {
        const emText = tokens[0].text || '';
        if (!emText.toLowerCase().startsWith('example:')) {
            return 'date-subtitle'; // Italic date line
        }
    }
    return 'subtitle';
}

/**
 * Parse marked inline tokens into IR spans.
 */
function parseInlineTokens(tokens) {
    const spans = [];

    for (const token of tokens) {
        switch (token.type) {
            case 'paragraph':
                // Loose lists wrap items in paragraphs — flatten
                if (token.tokens) {
                    spans.push(...parseInlineTokens(token.tokens));
                } else if (token.text) {
                    spans.push(...parseInlineText(token.text));
                }
                break;

            case 'text':
                // Re-parse text tokens — marked sometimes misses inline formatting in lists
                spans.push(...parseInlineText(token.text));
                break;

            case 'strong': {
                const boldText = token.text;
                const isLabel = boldText.trim().endsWith(':');
                spans.push({ type: 'bold', text: boldText, isLabel });
                break;
            }

            case 'em':
                spans.push({ type: 'italic', text: token.text });
                break;

            case 'codespan':
                spans.push({ type: 'code', text: token.text });
                break;

            case 'link': {
                const href = token.href || '';
                const internal = href.startsWith('#');
                spans.push({
                    type: 'link',
                    text: token.text,
                    href,
                    internal,
                    anchorId: internal ? generateAnchorId(href.substring(1)) : undefined
                });
                break;
            }

            default:
                if (token.raw) {
                    spans.push({ type: 'text', text: token.raw });
                }
        }
    }

    return spans;
}

/**
 * Regex-based fallback inline parsing for plain text strings.
 * Handles **bold**, *italic*, `code`, [link](url), and plain text.
 */
function parseInlineText(text) {
    const spans = [];
    const regex = /\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[([^\]]+)\]\(([^)]+)\)|([^*`\[]+)/g;
    let match;

    while ((match = regex.exec(text)) !== null) {
        if (match[1]) {
            // Bold
            const boldText = match[1];
            const isLabel = boldText.trim().endsWith(':');
            spans.push({ type: 'bold', text: boldText, isLabel });
        } else if (match[2]) {
            // Italic
            spans.push({ type: 'italic', text: match[2] });
        } else if (match[3]) {
            // Code
            spans.push({ type: 'code', text: match[3] });
        } else if (match[4] && match[5]) {
            // Link
            const href = match[5];
            const internal = href.startsWith('#');
            spans.push({
                type: 'link',
                text: match[4],
                href,
                internal,
                anchorId: internal ? generateAnchorId(href.substring(1)) : undefined
            });
        } else if (match[6]) {
            spans.push({ type: 'text', text: match[6] });
        }
    }

    return spans.length > 0 ? spans : [{ type: 'text', text }];
}

// ============================================================================
// HELPERS
// ============================================================================

/**
 * Generate a consistent, valid bookmark/anchor ID from heading text.
 * Limits to 40 chars (bm_ + 37 chars) for Word compatibility.
 */
function generateAnchorId(text) {
    const rawSlug = text.toLowerCase().replace(/[\s-]/g, '_').replace(/[^\w]/g, '');
    const truncatedSlug = rawSlug.substring(0, 35);
    return `bm_${truncatedSlug}`;
}

/**
 * Extract plain text from an array of spans (for index computation).
 */
function spansToPlainText(spans) {
    return spans.map(s => s.text).join('');
}

module.exports = { parseMarkdown, generateAnchorId, spansToPlainText, parseInlineText };
