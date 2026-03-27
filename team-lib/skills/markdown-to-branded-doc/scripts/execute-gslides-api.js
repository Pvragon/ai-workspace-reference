#!/usr/bin/env node

/**
 * Google Slides Plan Executor (gws CLI)
 * @version 0.1.0
 * @date 2026-03-19
 *
 * Template-copy approach: copies a branded slide template, clears example
 * slides, then creates new slides from layouts based on markdown content.
 *
 * Usage:
 *   node execute-gslides-api.js <plan.json> [--folder <folderId>]
 */

const { execSync } = require('child_process');
const fs = require('fs');

// ============================================================================
// CONSTANTS
// ============================================================================

const TEMPLATE_IDS = {
    'slides-informational': '1BhiG8yCbVUrNu0t91mJl__Ic9Uz7P1kpe7Q_Ey2Uij8',
    'slides-formal': '1BhiG8yCbVUrNu0t91mJl__Ic9Uz7P1kpe7Q_Ey2Uij8'  // same template for now
};

// Map layout display names to their object IDs (from the Pvragon template)
// These get populated dynamically from the copied presentation
let LAYOUTS = {};

// ============================================================================
// MAIN
// ============================================================================

function main() {
    const args = process.argv.slice(2);

    if (args.length < 1) {
        console.log('Usage: node execute-gslides-api.js <plan.json> [--folder <folderId>]');
        process.exit(1);
    }

    const planPath = args[0];
    let folderId = null;

    for (let i = 1; i < args.length; i++) {
        if (args[i] === '--folder' && args[i + 1]) {
            folderId = args[++i];
        }
    }

    if (!fs.existsSync(planPath)) {
        console.error(`Plan file not found: ${planPath}`);
        process.exit(1);
    }

    const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
    console.log(`Executing slide plan: ${planPath}`);
    console.log(`Title: ${plan.title}`);
    console.log(`Brand: ${plan.brand}`);
    console.log(`Slides: ${plan.slides.length}`);

    // Step 1: Copy the template
    const templateType = plan.templateType || 'slides-informational';
    const templateId = TEMPLATE_IDS[templateType];
    if (!templateId) {
        console.error(`No template found for type: ${templateType}`);
        process.exit(1);
    }

    const presentationId = copyTemplate(templateId, plan.title);
    console.log(`\nCreated presentation: ${presentationId} (from template)`);

    // Step 2: Load layout mappings from the copied presentation
    loadLayouts(presentationId);
    console.log(`Loaded ${Object.keys(LAYOUTS).length} layouts`);

    // Step 3: Delete all example slides (keep only layouts/masters)
    deleteExampleSlides(presentationId);
    console.log('Cleared example slides');

    // Step 4: Create slides from the plan
    for (let i = 0; i < plan.slides.length; i++) {
        const slide = plan.slides[i];
        createSlide(presentationId, slide, i);
    }
    console.log(`Created ${plan.slides.length} slides`);

    // Step 5: Move to folder if specified
    if (folderId) {
        moveToFolder(presentationId, folderId);
        console.log(`Moved to folder: ${folderId}`);
    }

    const url = `https://docs.google.com/presentation/d/${presentationId}/edit`;
    console.log(`\nPresentation URL: ${url}`);
    console.log(JSON.stringify({ presentationId, url, title: plan.title }));
}

// ============================================================================
// TEMPLATE & LAYOUT HELPERS
// ============================================================================

function copyTemplate(templateId, title) {
    const response = gws('drive', 'files', 'copy', {
        fileId: templateId,
        name: title,
        fields: 'id'
    });
    return response.id;
}

function loadLayouts(presentationId) {
    const pres = gws('slides', 'presentations', 'get', { presentationId });
    for (const layout of (pres.layouts || [])) {
        const name = layout.layoutProperties?.displayName || '';
        if (name) {
            LAYOUTS[name.toLowerCase().trim()] = layout.objectId;

            // Also index placeholder info for each layout
            const placeholders = [];
            for (const el of (layout.pageElements || [])) {
                if (el.shape?.placeholder) {
                    placeholders.push({
                        objectId: el.objectId,
                        type: el.shape.placeholder.type,
                        index: el.shape.placeholder.index
                    });
                }
            }
            LAYOUTS[`${name.toLowerCase().trim()}_placeholders`] = placeholders;
        }
    }
}

function deleteExampleSlides(presentationId) {
    const pres = gws('slides', 'presentations', 'get', { presentationId });
    const slides = pres.slides || [];
    if (slides.length === 0) return;

    const requests = slides.map(s => ({
        deleteObject: { objectId: s.objectId }
    }));

    gws('slides', 'presentations', 'batchUpdate', { presentationId }, { requests });
}

// ============================================================================
// SLIDE CREATION
// ============================================================================

/**
 * Pick the best layout for a slide based on its content.
 *
 * Layout selection logic:
 *   - 'title' → Title Slide
 *   - 'section' → Title + Content (section divider)
 *   - 'content' → Title + Subtitle + Content (default for body slides)
 *   - 'two-column' → Two Column Content Slides 1
 *   - 'table' → Title + Content (tables rendered as text)
 *   - 'blank' → Blank
 */
function selectLayout(slide) {
    const type = slide.layout || 'content';

    const layoutMap = {
        'title': 'title slide',
        'section': 'title + content',
        'content': 'title + subtitle + content',
        'two-column': 'two column content slides 1',
        'table': 'title + content',
        'blank': 'blank'
    };

    const layoutName = layoutMap[type] || 'title + subtitle + content';
    const layoutId = LAYOUTS[layoutName];

    if (!layoutId) {
        // Fallback to blank
        console.warn(`  Warning: layout "${layoutName}" not found, using blank`);
        return LAYOUTS['blank'] || null;
    }

    return layoutId;
}

function createSlide(presentationId, slide, index) {
    const layoutId = selectLayout(slide);
    const slideId = `slide_${index}_${Date.now()}`;

    // Create the slide from the layout
    const createRequests = [{
        createSlide: {
            objectId: slideId,
            insertionIndex: index,
            slideLayoutReference: {
                layoutId: layoutId
            }
        }
    }];

    gws('slides', 'presentations', 'batchUpdate', { presentationId }, { requests: createRequests });

    // Now populate the slide with text
    // Get the created slide to find its placeholder element IDs
    const pres = gws('slides', 'presentations', 'get', { presentationId });
    const createdSlide = pres.slides?.find(s => s.objectId === slideId);
    if (!createdSlide) {
        console.warn(`  Warning: could not find created slide ${slideId}`);
        return;
    }

    const textRequests = [];

    // Find placeholders on this slide
    const placeholders = {};
    for (const el of (createdSlide.pageElements || [])) {
        if (el.shape?.placeholder) {
            const pType = el.shape.placeholder.type;
            placeholders[pType] = el.objectId;
        }
        // Also match text boxes by their existing content patterns
        if (el.shape?.text) {
            let existingText = '';
            for (const te of (el.shape.text.textElements || [])) {
                if (te.textRun) existingText += te.textRun.content;
            }
            existingText = existingText.trim().toLowerCase();
            if (existingText.includes('title') || existingText.includes('presentation')) {
                if (!placeholders['TITLE']) placeholders['_title_box'] = el.objectId;
            }
            if (existingText.includes('sub-title') || existingText.includes('subtitle')) {
                if (!placeholders['SUBTITLE']) placeholders['_subtitle_box'] = el.objectId;
            }
        }
    }

    // Insert title
    if (slide.title) {
        const titleId = placeholders['TITLE'] || placeholders['CENTERED_TITLE'] || placeholders['_title_box'];
        if (titleId) {
            textRequests.push({
                insertText: {
                    objectId: titleId,
                    text: slide.title,
                    insertionIndex: 0
                }
            });
        }
    }

    // Insert subtitle
    if (slide.subtitle) {
        const subtitleId = placeholders['SUBTITLE'] || placeholders['_subtitle_box'];
        if (subtitleId) {
            textRequests.push({
                insertText: {
                    objectId: subtitleId,
                    text: slide.subtitle,
                    insertionIndex: 0
                }
            });
        }
    }

    // Insert body content
    if (slide.body) {
        const bodyId = placeholders['BODY'] || placeholders['OBJECT'];
        if (bodyId) {
            textRequests.push({
                insertText: {
                    objectId: bodyId,
                    text: slide.body,
                    insertionIndex: 0
                }
            });
        }
    }

    if (textRequests.length > 0) {
        gws('slides', 'presentations', 'batchUpdate', { presentationId }, { requests: textRequests });
    }
}

// ============================================================================
// GWS CLI HELPER
// ============================================================================

function gws(service, resource, method, params, body) {
    let cmd = `gws ${service} ${resource} ${method}`;

    if (params) {
        cmd += ` --params '${JSON.stringify(params)}'`;
    }

    // Use a temp file for request body to avoid shell quoting issues
    // (content may contain apostrophes, parentheses, etc.)
    let bodyFile = null;
    if (body) {
        bodyFile = `/tmp/gws-body-${process.pid}-${Date.now()}.json`;
        fs.writeFileSync(bodyFile, JSON.stringify(body));
        cmd += ` --json "$(cat ${bodyFile})"`;

    }

    const maxRetries = 3;
    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            const output = execSync(cmd, {
                encoding: 'utf8',
                maxBuffer: 50 * 1024 * 1024
            });
            if (bodyFile) try { fs.unlinkSync(bodyFile); } catch (_) {}
            return parseGwsOutput(output);
        } catch (err) {
            const stderr = err.stderr || '';
            const stdout = err.stdout || '';
            if (stdout.includes('"code": 429') || stderr.includes('429')) {
                const wait = 15 * (attempt + 1);
                console.log(`  Rate limited, waiting ${wait}s...`);
                execSync(`sleep ${wait}`);
                continue;
            }
            if (bodyFile) try { fs.unlinkSync(bodyFile); } catch (_) {}
            throw err;
        }
    }
}

function parseGwsOutput(output) {
    const trimmed = output.trim();
    const jsonStart = trimmed.indexOf('{');
    if (jsonStart === -1) {
        const arrStart = trimmed.indexOf('[');
        if (arrStart === -1) return {};
        try { return JSON.parse(trimmed.substring(arrStart)); } catch { return {}; }
    }
    try {
        return JSON.parse(trimmed.substring(jsonStart));
    } catch {
        return {};
    }
}

function moveToFolder(fileId, folderId) {
    const file = gws('drive', 'files', 'get', { fileId, fields: 'parents' });
    const currentParents = (file.parents || []).join(',');
    gws('drive', 'files', 'update', {
        fileId,
        addParents: folderId,
        removeParents: currentParents,
        fields: 'id,parents'
    });
}

// ============================================================================

main();
