#!/usr/bin/env node
// Horizontal-overflow measurement for a web page, at multiple breakpoints, via the
// Chrome DevTools Protocol driven with Node's built-in WebSocket (Node >=21). Needs NO
// playwright/puppeteer install — just a Chromium binary. Headless SCREENSHOTS render
// black in some WSL/headless envs, so we measure DOM metrics instead: the definitive
// horizontal-overflow test is document scrollWidth vs clientWidth at each width.
//
// Usage:
//   node measure_overflow_web.mjs <url> [w1,w2,...]   (default widths 2560,1440,768,375)
// Env:
//   CHROME=/path/to/chrome   (else tries common ms-playwright cache locations)
// Exit code: 0 if no width overflows, 1 if any does — so it can gate CI / iterate-fix.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { globSync } from 'node:fs';

const URL = process.argv[2];
if (!URL) { console.error('usage: node measure_overflow_web.mjs <url> [widths]'); process.exit(2); }
const WIDTHS = (process.argv[3] || '2560,1440,768,375').split(',').map(Number);
const PORT = 9223 + Math.floor((Date.now() % 500));   // avoid clashing with a live browser
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function findChrome() {
  if (process.env.CHROME && existsSync(process.env.CHROME)) return process.env.CHROME;
  const pats = [
    process.env.HOME + '/.cache/ms-playwright/chromium-*/chrome-linux*/chrome',
    '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome',
  ];
  for (const p of pats) { const hits = globSync(p); if (hits.length) return hits.sort().pop(); }
  throw new Error('no chromium binary found (set CHROME=/path/to/chrome)');
}

const MEASURE = `(function(){
  var d=document.documentElement, cw=d.clientWidth;
  var sw=Math.max(d.scrollWidth, document.body.scrollWidth);
  var bad=[]; var all=document.querySelectorAll('body *');
  for(var i=0;i<all.length;i++){var r=all[i].getBoundingClientRect();
    if(r.right>cw+2){var c=(all[i].className&&all[i].className.toString)?all[i].className.toString():'';
      bad.push(all[i].tagName+(c?'.'+c.trim().split(/\\s+/)[0]:'')+' right='+Math.round(r.right));}}
  return JSON.stringify({vw:cw, scrollWidth:sw, overflow: sw>cw+2, rightOverflowers: bad.slice(0,8)});
})()`;

const chrome = spawn(findChrome(), ['--headless=new', `--remote-debugging-port=${PORT}`,
  '--no-sandbox', '--disable-gpu', '--no-first-run', '--disable-extensions',
  '--window-size=1440,1400', URL], { stdio: 'ignore' });

async function pageWs() {
  for (let i = 0; i < 40; i++) {
    try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const pg = l.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
      if (pg) return pg.webSocketDebuggerUrl; } catch {}
    await sleep(250);
  }
  throw new Error('devtools page target never appeared');
}
function client(ws) {
  let id = 0; const pending = new Map();
  ws.addEventListener('message', (ev) => { const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
  return (method, params = {}) => new Promise((res) => { const mid = ++id; pending.set(mid, res); ws.send(JSON.stringify({ id: mid, method, params })); });
}

(async () => {
  let bad = false;
  try {
    const ws = new WebSocket(await pageWs());
    await new Promise((r) => ws.addEventListener('open', r, { once: true }));
    const send = client(ws);
    await send('Page.enable'); await send('Runtime.enable'); await sleep(1500);
    const out = {};
    for (const w of WIDTHS) {
      await send('Emulation.setDeviceMetricsOverride', { width: w, height: 1400, deviceScaleFactor: 1, mobile: w <= 768 });
      await sleep(450);
      const r = await send('Runtime.evaluate', { expression: MEASURE, returnByValue: true });
      const m = r && r.result ? JSON.parse(r.result.value) : { error: 'no result' };
      out[w] = m; if (m.overflow) bad = true;
    }
    console.log(JSON.stringify(out, null, 2));
  } catch (e) { console.log(JSON.stringify({ error: String(e && e.message || e) })); bad = true; }
  finally { chrome.kill('SIGKILL'); }
  process.exit(bad ? 1 : 0);
})();
