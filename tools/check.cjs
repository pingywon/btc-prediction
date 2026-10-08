// Render the built page and fail on the things a reader would notice.
//   PUPPETEER=/path/to/node_modules/puppeteer-core node tools/check.cjs [url]
const path = require('path');
const fs = require('fs');
const puppeteer = require(process.env.PUPPETEER || 'puppeteer-core');
const ROOT = path.join(__dirname, '..');
const URL = process.argv[2] || 'file://' + path.join(ROOT, 'index.html');
const OUT = path.join(ROOT, '.qa');
fs.mkdirSync(OUT, { recursive: true });
const version = fs.readFileSync(path.join(ROOT, 'VERSION'), 'utf8').trim();

(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/chromium',
    headless: 'new', args: ['--no-sandbox', '--hide-scrollbars'] });
  const fails = [];
  for (const [name, w, h, scheme] of [['desktop-light', 1440, 900, 'light'], ['desktop-dark', 1440, 900, 'dark'], ['phone', 390, 844, 'light']]) {
    const page = await browser.newPage();
    await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }]);
    const errs = [];
    page.on('pageerror', e => errs.push(String(e)));
    page.on('requestfailed', r => errs.push('failed ' + r.url()));
    await page.goto(URL, { waitUntil: 'networkidle0', timeout: 60000 });
    await page.evaluate(async () => {
      document.querySelectorAll('img').forEach(i => { i.loading = 'eager'; });
      await Promise.all([...document.images].map(i => i.decode().catch(() => {})));
      await document.fonts.ready;
    });
    const r = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      broken: [...document.images].filter(i => !i.naturalWidth).map(i => i.getAttribute('src')),
      footer: document.querySelector('footer .ver').textContent,
      tokens: (document.body.innerHTML.match(/\{\{[A-Z_]+\}\}/g) || []).length,
      height: document.documentElement.scrollHeight,
      words: document.querySelector('.wrap').innerText.split(/\s+/).length,
    }));
    if (r.overflow > 0) fails.push(`${name}: page scrolls sideways by ${r.overflow}px`);
    if (r.broken.length) fails.push(`${name}: broken images ${r.broken}`);
    if (r.tokens) fails.push(`${name}: unfilled tokens`);
    if (!r.footer.includes('v' + version)) fails.push(`${name}: footer does not show v${version}`);
    if (errs.length) fails.push(`${name}: ${errs.slice(0, 3).join(' | ')}`);
    await page.screenshot({ path: path.join(OUT, name + '.png'), fullPage: true });
    console.log(`${name}  ${w}px  height ${r.height}  words ${r.words}  footer "${r.footer}"`);
    if (name === 'desktop-light') {
      await page.focus('.db-row[tabindex]');
      const tip = await page.$eval('#tip', t => (getComputedStyle(t).display !== 'none' ? t.textContent : ''));
      if (!/won/.test(tip)) fails.push('tooltip did not open on focus');
      console.log('tooltip:', tip);
    }
    await page.close();
  }
  await browser.close();
  if (fails.length) { console.error('FAIL\n' + fails.join('\n')); process.exit(1); }
  console.log('all checks passed');
})().catch(e => { console.error(e); process.exit(1); });
