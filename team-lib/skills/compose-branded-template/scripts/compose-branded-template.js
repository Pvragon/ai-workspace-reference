#!/usr/bin/env node

/**
 * Branded Template Composer v2
 *
 * Composes base + type-override templates with brand tokens to produce
 * fully resolved branded templates. Uses tokenRef dot-path resolution
 * against brand-tokens.json and applies brand preference fan-out.
 *
 * Flow:
 *   1. Load base template (via $extends in type override)
 *   2. Deep merge base + type override (override wins, null removes)
 *   3. Resolve all tokenRef dot-paths against brand-tokens.json
 *   4. Apply brand preference fan-out (docs/slides settings → template properties)
 *   5. Write fully resolved branded template
 *
 * Usage:
 *   node compose.js --brand <name> --type <type>
 *   node compose.js --brand <name> --all
 *   node compose.js --brand <name> --type <type> --dry-run
 *
 * @version 2.1.0
 * @created 2026-03-14
 * @updated 2026-03-24
 */

const fs = require('fs');
const path = require('path');

// ============================================================================
// CONSTANTS
// ============================================================================

const { execSync } = require('child_process');

const COMPOSER_VERSION = '2.1.0';
const WORKSPACE_ROOT = path.resolve(__dirname, '..', '..', '..');
const TEMPLATES_DIR = path.resolve(__dirname, '..', 'templates');
const COMPANIES_DIR = path.resolve(WORKSPACE_ROOT, 'context', 'indexed', 'companies');
const APPS_SCRIPT_DIR = path.resolve(WORKSPACE_ROOT, 'integrations', 'apps-script');

// Shared page-number starter template (brand-independent — auto-updating page numbers
// cannot be inserted by any Google API, so this single template is reused across all brands)
const SHARED_PAGE_NUM_TEMPLATE_ID = '1ece9BQ7ouVm0Zg-YCxGaM0REjPuz_yl4q8f1oYLH2i4';

// Template types that use page numbers (all doc types except letterhead)
const PAGE_NUM_TYPES = ['doc-report', 'doc-report-cover', 'doc-legal'];

const ALL_TEMPLATE_TYPES = [
    'doc-report',
    'doc-report-cover',
    'doc-letterhead',
    'doc-legal',
    'slides-informational',
    'slides-formal',
    'html-presentation'
];

// ============================================================================
// MAIN
// ============================================================================

function main() {
    const args = parseArgs(process.argv.slice(2));

    if (!args.brand) {
        console.error('Error: --brand <name> is required');
        printUsage();
        process.exit(1);
    }

    if (!args.type && !args.all) {
        console.error('Error: --type <type> or --all is required');
        printUsage();
        process.exit(1);
    }

    // Load brand tokens
    const brandDir = path.join(COMPANIES_DIR, args.brand, 'brand');
    const tokensPath = path.join(brandDir, 'brand-tokens.json');
    if (!fs.existsSync(tokensPath)) {
        console.error(`Error: brand-tokens.json not found: ${tokensPath}`);
        console.error('Run parse-guidelines.js first to generate brand tokens.');
        process.exit(1);
    }
    const brandTokens = JSON.parse(fs.readFileSync(tokensPath, 'utf8'));

    // Determine which types to compose
    const types = args.all ? ALL_TEMPLATE_TYPES : [args.type];

    // Validate --type
    if (!args.all && args.type && !ALL_TEMPLATE_TYPES.includes(args.type)) {
        console.error(`Error: Unknown template type "${args.type}"`);
        console.error(`Valid types: ${ALL_TEMPLATE_TYPES.join(', ')}`);
        process.exit(1);
    }

    // Snapshot existing googleDocTemplates BEFORE composition overwrites the files
    const existingGoogleDocTemplates = snapshotExistingGoogleDocTemplates(args.brand, types);

    // Compose each template
    const results = [];
    for (const type of types) {
        const result = composeTemplate(type, brandTokens, brandDir, args);
        results.push(result);
    }

    // Inject googleDocTemplates into composed outputs
    if (!args.dryRun && !args.skipStarterTemplates) {
        const googleDocTemplates = resolveGoogleDocTemplates(args, brandTokens, brandDir, types, existingGoogleDocTemplates);
        if (googleDocTemplates) {
            injectGoogleDocTemplates(args.brand, types, googleDocTemplates);
        }
    }

    // Print summary
    console.log('\n========================================');
    console.log('Composition Summary');
    console.log('========================================');
    console.log(`Brand: ${brandTokens.company?.name || args.brand}`);
    console.log(`Mode: ${args.dryRun ? 'DRY RUN' : 'WRITE'}`);
    console.log('');

    for (const r of results) {
        const status = r.error ? 'FAILED' : (r.warnings.length > 0 ? `OK (${r.warnings.length} warnings)` : 'OK');
        console.log(`  ${r.type}: ${status}`);
        if (r.error) {
            console.log(`    Error: ${r.error}`);
        }
        for (const w of r.warnings) {
            console.log(`    Warning: ${w}`);
        }
        if (r.outputPath && !r.error) {
            console.log(`    -> ${r.outputPath}`);
        }
    }

    const hasErrors = results.some(r => r.error);
    if (hasErrors) process.exit(1);
}

// ============================================================================
// TEMPLATE COMPOSITION
// ============================================================================

function composeTemplate(type, brandTokens, brandDir, args) {
    const result = { type, warnings: [], outputPath: null, error: null };

    try {
        // Load type override template
        const typePath = path.join(TEMPLATES_DIR, `${type}.json`);
        if (!fs.existsSync(typePath)) {
            result.error = `Template not found: ${typePath}`;
            return result;
        }
        const typeTemplate = JSON.parse(fs.readFileSync(typePath, 'utf8'));

        // Step 1: Merge base + type override
        let merged;
        if (typeTemplate.$extends) {
            const basePath = path.join(TEMPLATES_DIR, `${typeTemplate.$extends}.json`);
            if (!fs.existsSync(basePath)) {
                result.error = `Base template not found: ${basePath}`;
                return result;
            }
            const baseTemplate = JSON.parse(fs.readFileSync(basePath, 'utf8'));
            merged = deepMerge(baseTemplate, typeTemplate);
        } else {
            // Standalone template (e.g., html-presentation)
            merged = JSON.parse(JSON.stringify(typeTemplate));
        }

        // Step 2: Build resolution context
        const context = {
            brandTokens,
            brandDir,
            warnings: [],
            resolvedCache: {}
        };

        // Step 3: Resolve all tokenRefs
        const resolved = resolveTokenRefs(merged, context);

        // Step 4: Apply brand preference fan-out
        // Pass the raw type template so preferences can skip values the type explicitly set
        const templateBase = type.startsWith('doc-') ? 'doc' :
                             type.startsWith('slides-') ? 'slides' :
                             type.startsWith('html-') ? 'html' : null;
        if (templateBase) {
            applyPreferences(resolved, brandTokens, templateBase, context, typeTemplate);
        }

        // Build composed output
        const composed = {
            $schema: 'branded-template-v2',
            composedFrom: {
                template: type,
                templateVersion: typeTemplate.templateVersion || '2.0.0',
                base: typeTemplate.$extends || null,
                brand: brandTokens.company?.name || args.brand,
                brandSlug: args.brand,
                tokensVersion: brandTokens.$generated?.guidelinesVersion || 'unknown',
                tokensCoverage: brandTokens.$generated?.coverage?.percent || null,
                composedAt: new Date().toISOString(),
                composerVersion: COMPOSER_VERSION
            }
        };

        // Copy all resolved properties except metadata
        for (const [key, value] of Object.entries(resolved)) {
            if (['$schema', '$extends', 'templateType', 'templateVersion', 'description',
                 'baseType', 'baseVersion'].includes(key)) continue;
            composed[key] = value;
        }

        result.warnings = context.warnings;

        // Write output
        const outputDir = path.join(COMPANIES_DIR, args.brand, 'brand', 'templates');
        const outputPath = path.join(outputDir, `${type}.json`);
        result.outputPath = outputPath;

        if (!args.dryRun) {
            fs.mkdirSync(outputDir, { recursive: true });
            fs.writeFileSync(outputPath, JSON.stringify(composed, null, 4));
        }

    } catch (err) {
        result.error = err.message;
    }

    return result;
}

// ============================================================================
// DEEP MERGE
// ============================================================================

/**
 * Deep merge base + override. Override values win at leaf level.
 * null in override explicitly removes the base value.
 * Arrays are replaced, not merged.
 */
function deepMerge(base, override) {
    if (override === null) return null;
    if (override === undefined) return base;
    if (typeof override !== 'object' || Array.isArray(override)) return override;
    if (typeof base !== 'object' || base === null || Array.isArray(base)) return override;

    const result = { ...base };
    for (const [key, value] of Object.entries(override)) {
        if (value === null) {
            result[key] = null;
        } else if (typeof value === 'object' && !Array.isArray(value) &&
                   typeof result[key] === 'object' && result[key] !== null && !Array.isArray(result[key])) {
            result[key] = deepMerge(result[key], value);
        } else {
            result[key] = value;
        }
    }
    return result;
}

// ============================================================================
// TOKEN REF RESOLUTION
// ============================================================================

/**
 * Recursively walk the template and resolve all { tokenRef: "dot.path" } objects.
 *
 * A tokenRef object like:
 *   { "tokenRef": "color.brand.primary", "fallback": "color.brand.accent" }
 *
 * Gets resolved by walking brand-tokens.json at the dot-path. If the node has
 * a $value, that's extracted. Colors have # stripped for Google Docs API compat.
 * Logos and company values are extracted as-is.
 */
function resolveTokenRefs(obj, context) {
    if (obj === null || obj === undefined) return obj;
    if (typeof obj !== 'object') return obj;
    if (Array.isArray(obj)) return obj.map(item => resolveTokenRefs(item, context));

    // Check if this object is a tokenRef
    if (obj.tokenRef !== undefined) {
        return resolveOneTokenRef(obj, context);
    }

    // Otherwise, recurse into all keys
    const resolved = {};
    for (const [key, value] of Object.entries(obj)) {
        resolved[key] = resolveTokenRefs(value, context);
    }
    return resolved;
}

/**
 * Resolve a single tokenRef object against brand-tokens.json.
 *
 * The tokenRef dot-path (e.g., "color.brand.primary") is walked through
 * the brand tokens object. If the destination has $value, that's extracted.
 * If not found and a fallback is specified, the fallback path is tried.
 *
 * Extra properties on the tokenRef object (besides tokenRef and fallback)
 * are preserved alongside the resolved value.
 */
function resolveOneTokenRef(obj, context) {
    const tokenPath = obj.tokenRef;
    const fallbackPath = obj.fallback;

    // Collect extra properties
    const extra = {};
    for (const [k, v] of Object.entries(obj)) {
        if (k !== 'tokenRef' && k !== 'fallback') {
            extra[k] = resolveTokenRefs(v, context);
        }
    }

    // Try primary path
    let value = lookupTokenPath(tokenPath, context.brandTokens);
    let usedFallback = false;

    // Try fallback if primary not found
    if (value === undefined && fallbackPath) {
        value = lookupTokenPath(fallbackPath, context.brandTokens);
        if (value !== undefined) {
            usedFallback = true;
        }
    }

    // Handle not found
    if (value === undefined) {
        context.warnings.push(`Unresolved tokenRef: "${tokenPath}"${fallbackPath ? ` (fallback "${fallbackPath}" also not found)` : ''}`);
        return { _unresolved: true, _tokenRef: tokenPath, _fallback: fallbackPath || null, ...extra };
    }

    // Handle null token values (explicitly undefined brand tokens)
    if (value === null) {
        return Object.keys(extra).length > 0 ? { value: null, ...extra } : null;
    }

    // Extract the resolved value
    const resolved = extractTokenValue(value, tokenPath);

    // If there are extra properties, wrap in an object
    if (Object.keys(extra).length > 0) {
        if (typeof resolved === 'object' && resolved !== null && !Array.isArray(resolved)) {
            return { ...resolved, ...extra };
        }
        return { value: resolved, ...extra };
    }

    return resolved;
}

/**
 * Walk a dot-path through an object. Returns undefined if not found.
 */
function lookupTokenPath(dotPath, obj) {
    const parts = dotPath.split('.');
    let current = obj;
    for (const part of parts) {
        if (current === null || current === undefined || typeof current !== 'object') {
            return undefined;
        }
        if (!(part in current)) return undefined;
        current = current[part];
    }
    return current;
}

/**
 * Extract the usable value from a brand token node.
 *
 * W3C tokens have $value/$type/$description — we extract $value.
 * Logo tokens are plain objects with file/width/height — used as-is.
 * Company/voice tokens are plain strings — used as-is.
 * Colors have # stripped for Google Docs API compatibility.
 */
function extractTokenValue(node, tokenPath) {
    // Plain value (string, number, boolean)
    if (typeof node !== 'object' || node === null) return node;

    // W3C token with $value
    if ('$value' in node) {
        const val = node.$value;
        // Strip # from color hex values
        if (node.$type === 'color' && typeof val === 'string' && val.startsWith('#')) {
            return val.substring(1);
        }
        return val;
    }

    // Logo token (has file property)
    if ('file' in node) {
        return { ...node };
    }

    // Heading token with $source (derived/fallback headings)
    if ('$source' in node && '$type' in node) {
        const val = node.$value;
        if (node.$type === 'color' && typeof val === 'string' && val.startsWith('#')) {
            return val.substring(1);
        }
        return val;
    }

    // Unknown structure — return as-is
    return node;
}

// ============================================================================
// PREFERENCE FAN-OUT
// ============================================================================

/**
 * Apply brand preferences to the resolved template. Preferences are
 * enumerated choices from brand-guidelines.md that map to specific
 * template property values.
 *
 * This is the "fan-out" — compact brand preferences expand into
 * concrete template property changes.
 */
function applyPreferences(template, brandTokens, templateBase, context, typeTemplate) {
    const prefs = brandTokens.preference || {};

    if (templateBase === 'doc') {
        applyDocPreferences(template, prefs.docs || {}, brandTokens, context, typeTemplate);
    } else if (templateBase === 'slides') {
        applySlidePreferences(template, prefs.slides || {}, brandTokens, context);
    }
    // HTML preferences are passed through as-is for the renderer
}

function applyDocPreferences(template, prefs, brandTokens, context, typeTemplate) {
    // Body font size — skip if the type template explicitly sets it
    const typeSetFontSize = typeTemplate?.documentSettings?.defaultFontSize ||
                            typeTemplate?.bodyText?.normal?.fontSize;
    if (prefs.bodyFontSize && !typeSetFontSize) {
        const size = parseInt(prefs.bodyFontSize, 10);
        if (size && template.documentSettings) {
            template.documentSettings.defaultFontSize = size;
        }
        if (size && template.bodyText?.normal) {
            template.bodyText.normal.fontSize = size;
        }
    }

    // Line spacing
    if (prefs.lineSpacing) {
        const spacing = parseInt(prefs.lineSpacing, 10);
        if (spacing && template.documentSettings) {
            template.documentSettings.lineSpacing = spacing;
        }
        if (spacing && template.bodyText?.normal) {
            template.bodyText.normal.lineSpacing = spacing;
        }
    }

    // Table headers
    if (prefs.tableHeaders && template.tables?.headerRow) {
        if (prefs.tableHeaders === 'restrained') {
            template.tables.headerRow.background = resolveColor('color.background.subtle', brandTokens);
            template.tables.headerRow.fontColor = resolveColor('color.text.default', brandTokens);
        } else if (prefs.tableHeaders === 'none') {
            template.tables.headerRow.background = resolveColor('color.background.default', brandTokens);
            template.tables.headerRow.fontColor = resolveColor('color.text.default', brandTokens);
            template.tables.headerRow.bold = false;
        }
        // 'branded' is the default — no changes needed
    }

    // Alternating rows
    if (prefs.alternatingRows === 'no' && template.tables) {
        template.tables.alternateRowBackground = null;
    }

    // Table density
    if (prefs.tableDensity === 'compact' && template.tables?.denseTable) {
        // Apply dense settings to all tables
        template.tables.cellPadding = template.tables.denseTable.cellPadding;
        template.tables.headerRow.fontSize = template.tables.denseTable.fontSize;
        template.tables.bodyRow.fontSize = template.tables.denseTable.fontSize;
    }

    // Accent on labels
    if (prefs.accentOnLabels === 'no' && template.inlineStyles?.boldLabel) {
        template.inlineStyles.boldLabel.color = resolveColor('color.text.default', brandTokens);
    }

    // Decorative rules
    if (prefs.decorativeRules === 'no') {
        template.horizontalRule = null;
    }

    // Callouts
    if (prefs.callouts === 'no') {
        template.callouts = null;
    }

    // TOC default — only apply if template supports TOC and doesn't explicitly override
    if (prefs.tocDefault === 'yes' && template.tocSupport && !template.tocSupport._explicitOverride) {
        template.tocSupport.enabled = true;
    }
}

function applySlidePreferences(template, prefs, brandTokens, context) {
    const bgMap = {
        'primary': 'color.brand.primary',
        'dark': 'color.text.default',
        'white': 'color.background.default',
        'accent': 'color.brand.accent',
        'light': 'color.background.subtle'
    };

    // Title background
    if (prefs.titleBackground && template.slideTypes?.title) {
        const tokenPath = bgMap[prefs.titleBackground];
        if (tokenPath) {
            template.slideTypes.title.background = resolveColor(tokenPath, brandTokens);
            // Adjust text colors for light backgrounds
            const isLight = ['white', 'light'].includes(prefs.titleBackground);
            if (isLight && template.slideTypes.title.title) {
                template.slideTypes.title.title.color = resolveColor('color.brand.primary', brandTokens);
            }
            if (isLight && template.slideTypes.title.subtitle) {
                template.slideTypes.title.subtitle.color = resolveColor('color.text.subtle', brandTokens);
            }
        }
    }

    // Content background
    if (prefs.contentBackground && template.slideTypes?.content) {
        const tokenPath = bgMap[prefs.contentBackground];
        if (tokenPath) {
            template.slideTypes.content.background = resolveColor(tokenPath, brandTokens);
        }
    }

    // Closing background
    if (prefs.closingBackground && template.slideTypes?.closing) {
        const tokenPath = bgMap[prefs.closingBackground];
        if (tokenPath) {
            template.slideTypes.closing.background = resolveColor(tokenPath, brandTokens);
        }
    }

    // Bullet marker color
    if (prefs.bulletMarker && template.slideTypes?.content?.bullets) {
        const markerMap = {
            'accent': 'color.brand.accent',
            'primary': 'color.brand.primary',
            'neutral': 'color.text.subtle'
        };
        const tokenPath = markerMap[prefs.bulletMarker];
        if (tokenPath) {
            template.slideTypes.content.bullets.markerColor = resolveColor(tokenPath, brandTokens);
        }
    }

    // Accent stripe
    if (prefs.accentStripe === 'no' && template.slideTypes?.content?.accentStripe) {
        template.slideTypes.content.accentStripe.enabled = false;
    }

    // Logo prominence
    if (prefs.logoProminence) {
        const scaleMap = { 'prominent': 2.0, 'subtle': 1.5, 'hidden': 0 };
        const opacityMap = { 'prominent': 0.6, 'subtle': 0.3, 'hidden': 0 };
        const scale = scaleMap[prefs.logoProminence];
        const opacity = opacityMap[prefs.logoProminence];
        if (scale !== undefined) {
            if (template.slideTypes?.title?.logo) template.slideTypes.title.logo.scaleFactor = scale;
            if (template.slideTypes?.closing?.logo) template.slideTypes.closing.logo.scaleFactor = scale;
        }
        if (opacity !== undefined) {
            if (template.slideTypes?.content?.logo) template.slideTypes.content.logo.opacity = opacity;
        }
    }

    // Footer content
    if (prefs.footerContent && template.slideFooter) {
        if (prefs.footerContent === 'numbers-only') {
            template.slideFooter.companyName = null;
        } else if (prefs.footerContent === 'none') {
            template.slideFooter.enabled = false;
        }
    }
}

/**
 * Helper: resolve a token path to a bare hex color value.
 */
function resolveColor(tokenPath, brandTokens) {
    const node = lookupTokenPath(tokenPath, brandTokens);
    if (!node) return null;
    if (typeof node === 'string') return node;
    if (node.$value) {
        const val = node.$value;
        return (typeof val === 'string' && val.startsWith('#')) ? val.substring(1) : val;
    }
    return null;
}

// ============================================================================
// GOOGLE DOC STARTER TEMPLATES
// ============================================================================

/**
 * Read existing googleDocTemplates from composed template files BEFORE
 * composition overwrites them. Returns { pageNumber, letterhead } or empty object.
 */
function snapshotExistingGoogleDocTemplates(brandSlug, types) {
    const result = {};
    const templatesDir = path.join(COMPANIES_DIR, brandSlug, 'brand', 'templates');

    for (const type of types) {
        const filePath = path.join(templatesDir, `${type}.json`);
        if (!fs.existsSync(filePath)) continue;
        try {
            const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
            if (data.googleDocTemplates) {
                Object.assign(result, data.googleDocTemplates);
            }
        } catch (e) { /* ignore */ }
    }

    return result;
}

/**
 * Resolve googleDocTemplates for the brand.
 *
 * - Page-number template: always the shared brand-independent ID
 * - Letterhead template: check existing composed templates for an ID;
 *   if none exists, create one via Apps Script (requires clasp)
 * - If --google-doc-templates was passed, use those IDs directly
 *
 * @returns {Object|null} { pageNumber, letterhead } or null if skipped
 */
function resolveGoogleDocTemplates(args, brandTokens, brandDir, types, existingGoogleDocTemplates) {
    // If manually provided, use those
    if (args.googleDocTemplates) {
        console.log('\nUsing manually provided googleDocTemplates');
        return {
            pageNumber: args.googleDocTemplates.pageNumber || SHARED_PAGE_NUM_TEMPLATE_ID,
            letterhead: args.googleDocTemplates.letterhead || null
        };
    }

    const result = {
        pageNumber: SHARED_PAGE_NUM_TEMPLATE_ID,
        letterhead: null
    };

    // Check if letterhead ID already exists from the pre-composition snapshot
    if (existingGoogleDocTemplates?.letterhead) {
        result.letterhead = existingGoogleDocTemplates.letterhead;
        console.log(`\nCarrying forward existing letterhead template ID: ${result.letterhead}`);
        return result;
    }

    // No existing letterhead ID — try to create one via Apps Script
    if (!types.includes('doc-letterhead')) {
        // Not composing letterhead this run, skip
        return result;
    }

    // Check if clasp is available
    try {
        execSync('which clasp', { stdio: 'pipe' });
    } catch (e) {
        console.log('\nWarning: clasp not installed — cannot create letterhead starter template.');
        console.log('Install @google/clasp and run `clasp login` to enable letterhead template creation.');
        console.log('Or pass --google-doc-templates \'{"letterhead":"<id>"}\' to provide an existing template ID.');
        return result;
    }

    // Check if .clasp.json exists in the apps-script directory
    if (!fs.existsSync(path.join(APPS_SCRIPT_DIR, '.clasp.json'))) {
        console.log(`\nWarning: Apps Script project not found at ${APPS_SCRIPT_DIR}`);
        console.log('Cannot create letterhead starter template.');
        return result;
    }

    // Build parameters for createLetterheadTemplate
    const companyJsonPath = path.join(COMPANIES_DIR, args.brand, 'company.json');
    let companyInfo = {};
    if (fs.existsSync(companyJsonPath)) {
        companyInfo = JSON.parse(fs.readFileSync(companyJsonPath, 'utf8'));
    }

    // Get company info from brand tokens as fallback
    const tokenCompany = brandTokens.company || {};
    const mergedCompanyInfo = {
        address: companyInfo.address || tokenCompany.address || null,
        email: companyInfo.email || tokenCompany.email || null,
        phone: companyInfo.phone || tokenCompany.phone || null,
        website: companyInfo.website || tokenCompany.website || null
    };

    const brandStyle = {
        primaryFont: brandTokens.typography?.font?.primary?.$value || 'Lato'
    };

    // Find a horizontal logo file for the brand
    const logoConfig = findBrandLogo(brandDir);

    const brandName = brandTokens.company?.name || companyInfo.name || args.brand;

    console.log(`\nCreating letterhead starter template for ${brandName}...`);

    // Call clasp to create the letterhead template
    const claspParams = JSON.stringify([brandName, mergedCompanyInfo, brandStyle, logoConfig, '']);
    try {
        const output = execSync(
            `clasp run-function createLetterheadTemplate --user run --params '${claspParams.replace(/'/g, "'\\''")}'`,
            { cwd: APPS_SCRIPT_DIR, encoding: 'utf8', timeout: 60000 }
        );

        // Parse the response — clasp outputs JS object notation (unquoted keys), not strict JSON
        // Extract the documentId directly via regex since the output isn't valid JSON
        const docIdMatch = output.match(/documentId:\s*'([^']+)'/);
        const docUrlMatch = output.match(/documentUrl:\s*'([^']+)'/);
        const noteMatch = output.match(/note:\s*'([^']+)'/);
        const response = {
            documentId: docIdMatch ? docIdMatch[1] : null,
            documentUrl: docUrlMatch ? docUrlMatch[1] : null,
            note: noteMatch ? noteMatch[1] : null
        };
        if (response.documentId) {
            result.letterhead = response.documentId;
            console.log(`  Created: ${response.documentUrl}`);
            if (response.note) {
                console.log(`  Note: ${response.note}`);
            }
        }
    } catch (e) {
        console.log(`  Warning: Failed to create letterhead template via Apps Script: ${e.message}`);
        console.log('  You can create one manually and pass --google-doc-templates \'{"letterhead":"<id>"}\'');
    }

    return result;
}

/**
 * Find a horizontal/full logo file in the brand assets directory.
 * Returns a logoConfig object for the Apps Script function, or null.
 */
function findBrandLogo(brandDir) {
    const assetsDir = path.join(brandDir, 'assets');
    if (!fs.existsSync(assetsDir)) return null;

    const files = fs.readdirSync(assetsDir);

    // Prefer: horizontal logo > full logo > any logo
    const priorities = [
        f => /horizontal/i.test(f) && !/white/i.test(f),
        f => /horizontal/i.test(f),
        f => /logo\.(png|jpg|jpeg)$/i.test(f) && !/white/i.test(f) && !/icon/i.test(f),
        f => /logo/i.test(f) && !/white/i.test(f) && !/icon/i.test(f)
    ];

    for (const test of priorities) {
        const match = files.find(test);
        if (match) {
            // Upload to Drive and return config
            const logoPath = path.join(assetsDir, match);
            const driveFileId = uploadLogotoDrive(logoPath, match);
            if (driveFileId) {
                return { driveFileId, widthPt: 150, heightPt: 95 };
            }
        }
    }

    return null;
}

/**
 * Upload a logo file to Google Drive and make it publicly readable.
 * Returns the Drive file ID, or null on failure.
 */
function uploadLogotoDrive(filePath, fileName) {
    try {
        // Convert to PNG if needed (WebP files with .png extension are common)
        let uploadPath = filePath;
        try {
            const fileOutput = execSync(`file "${filePath}"`, { encoding: 'utf8' });
            if (fileOutput.includes('Web/P') || fileOutput.includes('RIFF')) {
                // Convert WebP to actual PNG
                const tmpPath = `/tmp/_logo_upload_${Date.now()}.png`;
                execSync(`python3 -c "from PIL import Image; Image.open('${filePath}').save('${tmpPath}', 'PNG')"`, { encoding: 'utf8' });
                uploadPath = tmpPath;
            }
        } catch (e) { /* use original file */ }

        const rawOutput = execSync(
            `gws drive files create --json '{"name":"${fileName}","mimeType":"image/png"}' --upload "${uploadPath}"`,
            { encoding: 'utf8' }
        );
        // Filter out non-JSON lines (e.g., "Using keyring backend: keyring")
        const output = rawOutput.split('\n').filter(l => !l.startsWith('Using keyring')).join('\n');

        const result = JSON.parse(output);
        const fileId = result.id;

        if (fileId) {
            // Make publicly readable for Apps Script to fetch
            execSync(
                `gws drive permissions create --params '{"fileId":"${fileId}"}' --json '{"role":"reader","type":"anyone"}'`,
                { encoding: 'utf8', stdio: 'pipe' }
            );
        }

        return fileId;
    } catch (e) {
        console.log(`  Warning: Failed to upload logo: ${e.message}`);
        return null;
    }
}

/**
 * Inject googleDocTemplates into composed template files on disk.
 * Reads each composed JSON, adds/updates the googleDocTemplates field, writes back.
 */
function injectGoogleDocTemplates(brandSlug, types, googleDocTemplates) {
    const templatesDir = path.join(COMPANIES_DIR, brandSlug, 'brand', 'templates');

    for (const type of types) {
        const filePath = path.join(templatesDir, `${type}.json`);
        if (!fs.existsSync(filePath)) continue;

        const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));

        if (PAGE_NUM_TYPES.includes(type)) {
            data.googleDocTemplates = { pageNumber: googleDocTemplates.pageNumber || null };
        } else if (type === 'doc-letterhead') {
            data.googleDocTemplates = { letterhead: googleDocTemplates.letterhead || null };
        }

        fs.writeFileSync(filePath, JSON.stringify(data, null, 4) + '\n');
    }

    console.log('\nInjected googleDocTemplates into composed templates');
}

// ============================================================================
// CLI HELPERS
// ============================================================================

function parseArgs(argv) {
    const args = { brand: null, type: null, all: false, dryRun: false, skipStarterTemplates: false, googleDocTemplates: null };
    for (let i = 0; i < argv.length; i++) {
        switch (argv[i]) {
            case '--brand': args.brand = argv[++i]; break;
            case '--type': args.type = argv[++i]; break;
            case '--all': args.all = true; break;
            case '--dry-run': args.dryRun = true; break;
            case '--skip-starter-templates': args.skipStarterTemplates = true; break;
            case '--google-doc-templates': args.googleDocTemplates = JSON.parse(argv[++i]); break;
        }
    }
    return args;
}

function printUsage() {
    console.log(`
Usage:
  node compose.js --brand <name> --type <type>
  node compose.js --brand <name> --all
  node compose.js --brand <name> --all --dry-run

Options:
  --brand <name>                Brand slug (matches directory under context/indexed/companies/)
  --type <type>                 Template type: ${ALL_TEMPLATE_TYPES.join(', ')}
  --all                         Compose all template types for the brand
  --dry-run                     Validate and report without writing files
  --skip-starter-templates      Skip Google Doc starter template creation (re-compose tokens only)
  --google-doc-templates <json> Manually provide template IDs: '{"pageNumber":"...","letterhead":"..."}'
`);
}

// ============================================================================
// RUN
// ============================================================================

main();
