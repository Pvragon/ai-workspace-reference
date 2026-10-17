// verify_branded_html.mjs — render a built branded HTML document in headless Chromium (SwiftShader) in light/dark/mobile,
// report console errors + horizontal overflow, exercise the click-to-open viewer, save screenshots.
import { createRequire } from 'node:module';
const CLI = process.env.HOME + '/ai-workspace/team-lib/integrations/excalidraw-cli/node_modules';
const require = createRequire(CLI + '/anchor.cjs');
const { chromium } = require('playwright');
const FILE = process.argv[2];
const OUT = process.argv[3];
const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--disable-gpu'] });
for (const [theme, w] of [['dark', 1280], ['dark', 390]]) {
  const p = await b.newPage({ viewport: { width: w, height: 1000 }, colorScheme: theme });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { if (m.type() === 'error' && !/prez-header\.js/.test(m.text()) && !/ERR_FILE_NOT_FOUND/.test(m.text())) errs.push(m.text()); });
  await p.goto('file://' + FILE, { waitUntil: 'networkidle' });
  await p.waitForTimeout(300);
  const m = await p.evaluate(() => ({
    sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
    svgs: document.querySelectorAll('.canvas svg').length,
    h: document.documentElement.scrollHeight,
    font: (document.fonts && document.fonts.check('16px "Noto Sans"')) ? 'Noto Sans loaded' : 'NOT loaded', canvas: !!document.getElementById('wave-bg'),
    clipped: Array.from(document.querySelectorAll('.canvas svg foreignObject div')).filter(d => d.scrollHeight > d.clientHeight + 2).length
  }));
  console.log(theme, w, JSON.stringify(m), 'errors:', errs.length ? errs : 'none');
  await p.screenshot({ path: `${OUT}/prez-${theme}-${w}.png`, fullPage: true });
  // The viewer check needs a second .canvas; pages with no diagrams have none.
  if (theme === 'dark' && w === 1280 && await p.locator('.canvas').count() > 1) {
    await p.locator('.canvas').nth(1).click();
    await p.waitForTimeout(400);
    const v = await p.evaluate(() => ({ open: !document.querySelector('.viewer').hidden,
      title: document.querySelector('.vtitle').textContent, z: document.querySelector('.zlevel').textContent,
      svgInPan: !!document.querySelector('.viewer .pan svg') }));
    console.log('viewer:', JSON.stringify(v));
    await p.screenshot({ path: `${OUT}/prez-viewer.png` });
    await p.keyboard.press('Escape');
    await p.waitForTimeout(200);
    console.log('after esc: viewer hidden =', await p.evaluate(() => document.querySelector('.viewer').hidden),
      ', svg back in canvas =', await p.evaluate(() => document.querySelectorAll('.canvas svg').length));
  }
  await p.close();
}
await b.close();
