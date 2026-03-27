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
 * @returns {DocumentIR}
 *
 * DocumentIR shape:
 * {
 *   title: string | null,
 *   metadata: object | null,
 *   blocks: Block[]
 * }
 */
function parseMarkdown(mdContent) {
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
        if (metadata && !metadataInserted) {
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
                if (!reachedContent && !isFirstHeading) {
                    // Pre-content zone → subtitle paragraphs
                    const lines = token.text.split('\n');
                    lines.forEach(line => {
                        const inlineTokens = marked.lexer(line);
                        const subToken = (inlineTokens[0] && inlineTokens[0].tokens)
                            ? inlineTokens[0] : { text: line, tokens: [] };

                        const spans = parseInlineTokens(subToken.tokens || []);
                        const variant = classifySubtitle(line, subToken.tokens);

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

    // Fallback: insert metadata at end if never inserted
    if (metadata && !metadataInserted) {
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

        let spans;
        if (contentTokens.length > 0) {
            spans = parseInlineTokens(contentTokens);
        } else if (item.text) {
            spans = parseInlineText(item.text);
        } else {
            spans = [{ type: 'text', text: '' }];
        }

        const subListBlocks = subLists.map(sl => buildListBlock(sl, listId, level + 1));
        const isLast = index === token.items.length - 1;

        return { spans, subLists: subListBlocks, isLast };
    });

    return {
        type: 'list',
        ordered: token.ordered,
        listId: listId || (token.ordered ? 'numbered-list' : 'bullet-list'),
        level,
        items
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
