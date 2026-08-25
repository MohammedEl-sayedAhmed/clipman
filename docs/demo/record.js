// Record ONE clean loop of the Clipman reel to webm at 2560x1440.
// Usage: node record.js [#hash] [outBaseName]
const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

(async () => {
  const hash = process.argv[2] || '#capture';
  const base = process.argv[3] || 'clipman-demo';
  const dir = path.resolve(__dirname, 'rec');
  fs.mkdirSync(dir, { recursive: true });
  const file = 'file://' + path.resolve(__dirname, 'clipman-reel.html') + hash;

  const browser = await chromium.launch({
    channel: 'chrome',
    args: ['--force-color-profile=srgb', '--hide-scrollbars', '--disable-features=Translate', '--autoplay-policy=no-user-gesture-required'],
  });
  const VW = +(process.env.VW || 1920), VH = +(process.env.VH || 1080), DSF = +(process.env.DSF || 2);
  const ctx = await browser.newContext({
    viewport: { width: VW, height: VH },
    deviceScaleFactor: DSF,
    recordVideo: { dir, size: { width: VW, height: VH } },
  });
  const page = await ctx.newPage();
  await page.goto(file, { waitUntil: 'load' });
  await page.waitForTimeout(700);   // let intro paint
  // hold until the sequence reaches the outro brand card (deterministic end, load-independent)
  await page.waitForFunction(() => window.__done, null, { timeout: 90000 }).catch(() => {});
  await page.waitForTimeout(400);
  const vid = page.video();
  await ctx.close();                // flush the video file
  const src = await vid.path();
  const out = path.resolve(__dirname, base + '.webm');
  fs.copyFileSync(src, out);
  await browser.close();
  console.log('REC_OK ' + out);
})().catch(e => { console.error('REC_FAIL', e); process.exit(1); });
