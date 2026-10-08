// Draw img/og.png, the 1200x630 link-preview card, from tools/data.json.
//   PUPPETEER=/path/to/node_modules/puppeteer-core node tools/og.cjs
const path = require('path');
const fs = require('fs');
const puppeteer = require(process.env.PUPPETEER || 'puppeteer-core');
const ROOT = path.join(__dirname, '..');
const d = JSON.parse(fs.readFileSync(path.join(ROOT, 'tools', 'data.json'), 'utf8'));
const tile = (v, l) => `<div><b>${v.toFixed(1)}<small>%</small></b><span>${l}</span></div>`;
const html = `<!doctype html><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,100..900&display=swap" rel="stylesheet">
<style>
body{margin:0;width:1200px;height:630px;background:#eef1f5;color:#0f1a33;font-family:Archivo,sans-serif;display:flex;flex-direction:column;padding:54px 64px;box-sizing:border-box}
p{margin:0;font-size:26px;font-weight:600;color:#4a3aa7}
h1{margin:14px 0 0;font-weight:800;font-stretch:72%;font-size:104px;line-height:.96;letter-spacing:-.012em}
.t{display:flex;margin-top:auto;border:2px solid #0f1a33;background:#fff}
.t div{flex:1;padding:18px 26px 20px;border-right:1px solid #c3ccda}
.t div:last-child{border-right:0}
.t b{display:block;font-weight:800;font-stretch:72%;font-size:78px;line-height:1}
.t small{font-size:.5em}
.t span{display:block;margin-top:8px;font-size:23px;color:#3f4a66}
</style>
<p>BTC 15 · just for fun · ${d.rounds.toLocaleString('en-US')} rounds</p>
<h1>A coin flip, every 15 minutes.</h1>
<div class="t">${tile(d.yes_pct, 'closed YES')}${tile(d.flip_pct, 'flipped from the round before')}${tile(d.histcall.pct, 'right, calling by pattern')}</div>`;

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/chromium', headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: 'networkidle0' });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(ROOT, 'img', 'og.png') });
  await browser.close();
  console.log('wrote img/og.png');
})().catch(e => { console.error(e); process.exit(1); });
