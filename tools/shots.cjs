// Screenshots of a running BTC 15 for the page. Read-only: every non-GET request is
// aborted, so opening the Studio cannot save over the board that is on the server.
//
//   BTC15_URL=http://<host> PUPPETEER=/path/to/node_modules/puppeteer-core node tools/shots.cjs
const path = require('path');
const puppeteer = require(process.env.PUPPETEER || 'puppeteer-core');
const BASE = (process.env.BTC15_URL || '').replace(/\/$/, '');
if (!BASE) { console.error('set BTC15_URL to the running app'); process.exit(1); }
const OUT = path.join(__dirname, '..', 'img');
const W = 1440;

const SHOTS = [
  { name: 'classic', path: '/', clip: [0, 0, W, 1108] },
  { name: 'road', path: '/', sel: '.bigroad-section' },
  { name: 'histcall', path: '/', sel: '.histcall-card' },
  { name: 'studio', path: '/studio', clip: [0, 0, W, 1562] },
  { name: 'algo', path: '/algo', clip: [0, 0, W, 1000] },
];

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/chromium',
    headless: 'new', args: ['--no-sandbox', '--hide-scrollbars'] });
  let blocked = 0;
  const pages = {};
  for (const s of SHOTS) {
    let page = pages[s.path];
    if (!page) {
      page = pages[s.path] = await browser.newPage();
      await page.setViewport({ width: W, height: 1000, deviceScaleFactor: 2 });
      await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
      await page.setRequestInterception(true);
      page.on('request', r => { if (r.method() !== 'GET') { blocked++; r.abort(); } else r.continue(); });
      await page.goto(BASE + s.path, { waitUntil: 'networkidle2', timeout: 45000 });
      await new Promise(r => setTimeout(r, 6000));
    }
    let clip;
    if (s.sel) {
      const b = await page.$eval(s.sel, el => { const r = el.getBoundingClientRect(); return [r.x, r.y + scrollY, r.width, r.height]; });
      clip = [b[0] - 12, b[1] - 12, b[2] + 24, b[3] + 24];
    } else clip = s.clip;
    const file = path.join(OUT, `shot-${s.name}.webp`);
    await page.screenshot({ path: file, type: 'webp', quality: 86, captureBeyondViewport: true,
      clip: { x: clip[0], y: clip[1], width: clip[2], height: clip[3] } });
    console.log(`${s.name}  ${Math.round(clip[2])}x${Math.round(clip[3])}`);
  }
  console.log(`blocked write requests: ${blocked}`);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
