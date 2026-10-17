// Turn an Excalidraw-exported SVG into an HTML-embeddable, responsive, centered
// <figure> + inline SVG — for hand-composed HTML presentations and self-contained
// page outputs. Pure string transforms; no browser needed.
//
// The Excalidraw SVG already carries a viewBox and base64-embedded fonts, so it's
// self-contained. We only strip the fixed width/height (which would break mobile
// layout) and inject responsive styling. Use with a transparent background
// (`--no-bg`) so the diagram sits on the page/deck background.

/**
 * @param {string} svg   an Excalidraw exportToSvg string
 * @param {object} [opts]
 * @param {number} [opts.maxWidth]   cap width in px (default: the SVG's intrinsic viewBox width)
 * @param {boolean} [opts.center=true]
 * @param {string} [opts.className="excalidraw-diagram"]
 * @param {string} [opts.caption]    optional <figcaption> text
 * @returns {string} an HTML fragment
 */
export function svgToHtmlFigure(svg, opts = {}) {
  const { maxWidth, center = true, className = 'excalidraw-diagram', caption } = opts;

  const tagMatch = svg.match(/<svg\b[^>]*?>/);
  if (!tagMatch) return svg; // not an svg — return unchanged

  const tag = tagMatch[0];
  const vb = tag.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
  const intrinsicW = vb ? Math.round(parseFloat(vb[1])) : null;
  const capW = maxWidth || intrinsicW;

  // Operate ONLY on the root <svg> tag (inner elements may legitimately use
  // width/height): drop fixed dims, add responsive style.
  const newTag = tag
    .replace(/\swidth="[^"]*"/, '')
    .replace(/\sheight="[^"]*"/, '')
    .replace(/<svg\b/, '<svg style="width:100%;height:auto;display:block;margin:0 auto;"');

  const body = svg.replace(tag, newTag);

  const figStyle = [
    center ? 'text-align:center' : '',
    'margin:1.5rem auto',
    capW ? `max-width:${capW}px` : '',
  ].filter(Boolean).join(';');

  const cap = caption ? `\n  <figcaption>${caption}</figcaption>` : '';
  return `<figure class="${className}" style="${figStyle};">\n  ${body}${cap}\n</figure>`;
}
