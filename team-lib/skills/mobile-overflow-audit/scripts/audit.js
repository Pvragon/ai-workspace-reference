#!/usr/bin/env node
// Mobile overflow audit for Pvragon HTML presentations.
// Walks each .slide at a phone-landscape viewport and reports overflow.
//
// Usage:
//   node audit.js <url> [--viewport WxH] [--threshold N] [--all]
//
// See SKILL.md for full documentation.

const { chromium } = require('playwright');

function parseArgs(argv) {
  const args = { url: null, viewport: { w: 844, h: 390 }, threshold: 5, all: false };
  const positional = [];
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--viewport') {
      const m = (argv[++i] || '').match(/^(\d+)x(\d+)$/);
      if (!m) { console.error('--viewport must be WxH (e.g. 844x390)'); process.exit(2); }
      args.viewport = { w: parseInt(m[1], 10), h: parseInt(m[2], 10) };
    } else if (a === '--threshold') {
      args.threshold = parseInt(argv[++i], 10);
    } else if (a === '--all') {
      args.all = true;
    } else if (a.startsWith('--')) {
      console.error(`Unknown flag: ${a}`); process.exit(2);
    } else {
      positional.push(a);
    }
  }
  if (positional.length !== 1) {
    console.error('Usage: node audit.js <url> [--viewport WxH] [--threshold N] [--all]');
    process.exit(2);
  }
  args.url = positional[0];
  return args;
}

async function audit({ url, viewport, threshold, all }) {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: viewport.w, height: viewport.h } });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: 'load' });
  // Brief settle delay so transitions, fonts, etc. are stable
  await page.waitForTimeout(800);

  const results = await page.evaluate(() => {
    const slides = document.querySelectorAll('.slide');
    if (slides.length === 0) {
      return { error: 'No .slide elements found — is this a Pvragon HTML presentation?' };
    }
    const originalActive = document.querySelector('.slide.active');
    const out = [];
    slides.forEach((slide, idx) => {
      slides.forEach(s => s.classList.remove('active'));
      slide.classList.add('active');
      // force layout
      void slide.offsetHeight;
      const overflow = slide.scrollHeight - slide.clientHeight;
      const heading = (
        slide.querySelector('h1')?.textContent
        || slide.querySelector('h2')?.textContent
        || slide.querySelector('h3')?.textContent
        || '(no heading)'
      ).trim().substring(0, 80);
      // Collect distinct component classes from direct children
      const components = Array.from(new Set(
        Array.from(slide.querySelectorAll('*'))
          .map(el => el.className)
          .filter(cls => typeof cls === 'string' && cls.length > 0)
          .flatMap(cls => cls.split(/\s+/))
          .filter(cls => /^(bullet-list|stat-callout|diagram-container|node|memory-list|memory-item|quote-block|equation|equation-part|workspace-grid|workspace-card|cta-btn|flow-visual|flow-box|flow-row|tier-stack|tier-row|stack-grid|stack-card|dir-columns|dir-col)/.test(cls))
      )).sort();
      out.push({ idx, heading, scrollH: slide.scrollHeight, clientH: slide.clientHeight, overflow, components });
    });
    slides.forEach(s => s.classList.remove('active'));
    if (originalActive) originalActive.classList.add('active');
    return { slides: out };
  });

  await browser.close();

  if (results.error) {
    console.error(`ERROR: ${results.error}`);
    process.exit(1);
  }

  const slides = results.slides;
  const filtered = all ? slides : slides.filter(s => s.overflow > threshold);
  const worst = slides.reduce((m, s) => Math.max(m, s.overflow), 0);

  const report = {
    url,
    viewport: { w: viewport.w, h: viewport.h },
    slideCount: slides.length,
    worstOverflow: worst,
    threshold,
    overflowing: filtered,
  };
  console.log(JSON.stringify(report, null, 2));
  // Exit code 1 if any slide is overflowing > threshold (lets shell scripts gate on it)
  process.exit(filtered.length > 0 ? 1 : 0);
}

const args = parseArgs(process.argv);
audit(args).catch(e => {
  console.error('FAILED:', e.message);
  process.exit(1);
});
