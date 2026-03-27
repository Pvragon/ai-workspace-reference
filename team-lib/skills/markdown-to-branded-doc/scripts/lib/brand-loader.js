/**
 * Branded Template Loader
 * @version 1.0.0
 * @date 2026-03-19
 *
 * Loads pre-composed branded templates from the company context directory:
 *   context/indexed/companies/{brand}/brand/templates/{type}.json
 *
 * These templates are fully resolved — no token references, no merge logic.
 * The renderer reads one file and renders. See compose-branded-template skill.
 *
 * Usage:
 *   const template = loadBrandedTemplate('pvragon', 'doc-report');
 *   // template.documentSettings, template.headings, template.tables, etc.
 */

const fs = require('fs');
const path = require('path');

const CONTEXT_DIR = path.resolve(__dirname, '../../../../context/indexed/companies');
const DEFAULT_BRAND = 'pvragon';
const DEFAULT_TYPE = 'doc-report';

/**
 * Load a pre-composed branded template.
 *
 * @param {string} brandName - Company slug (e.g., 'pvragon', 'acme-corp')
 * @param {string} docType - Document type (e.g., 'doc-report', 'doc-legal', 'slides-formal')
 * @returns {object} Fully resolved branded template
 */
function loadBrandedTemplate(brandName, docType) {
    const brandDir = path.join(CONTEXT_DIR, brandName);

    if (!fs.existsSync(brandDir)) {
        const available = listAvailableBrands();
        console.error(`Brand not found: ${brandName}`);
        console.error(`Available brands: ${available.join(', ') || '(none)'}`);
        process.exit(1);
    }

    const templatePath = path.join(brandDir, 'brand', 'templates', `${docType}.json`);

    if (!fs.existsSync(templatePath)) {
        const available = listAvailableTypes(brandName);
        console.error(`Template not found: ${templatePath}`);
        console.error(`Available types for ${brandName}: ${available.join(', ') || '(none)'}`);
        process.exit(1);
    }

    try {
        const template = JSON.parse(fs.readFileSync(templatePath, 'utf8'));

        // Attach resolved paths for convenience
        template._brandDir = path.join(brandDir, 'brand');
        template._templatePath = templatePath;

        return template;
    } catch (err) {
        console.error(`Error parsing branded template: ${err.message}`);
        console.error(`File: ${templatePath}`);
        process.exit(1);
    }
}

/**
 * List available brand slugs (company directories that have brand/templates/).
 */
function listAvailableBrands() {
    if (!fs.existsSync(CONTEXT_DIR)) return [];
    return fs.readdirSync(CONTEXT_DIR).filter(name => {
        const templatesDir = path.join(CONTEXT_DIR, name, 'brand', 'templates');
        return fs.existsSync(templatesDir);
    });
}

/**
 * List available document types for a brand.
 */
function listAvailableTypes(brandName) {
    const templatesDir = path.join(CONTEXT_DIR, brandName, 'brand', 'templates');
    if (!fs.existsSync(templatesDir)) return [];
    return fs.readdirSync(templatesDir)
        .filter(f => f.endsWith('.json'))
        .map(f => f.replace('.json', ''));
}

module.exports = { loadBrandedTemplate, listAvailableBrands, listAvailableTypes, DEFAULT_BRAND, DEFAULT_TYPE, CONTEXT_DIR };
