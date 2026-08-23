const { chromium } = require('playwright-core');
const fs = require('fs');
const SRC = process.argv[2], OUT = process.argv[3];
const FPS = 30, DIR = '/tmp/frames';
(async () => {
  fs.rmSync(DIR, { recursive: true, force: true }); fs.mkdirSync(DIR, { recursive: true });
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  await p.goto('file://' + SRC);
  await p.evaluate(() => window.READY);
  const DUR = await p.evaluate(() => window.DUR || 32);
  const total = Math.round(FPS * DUR);
  for (let i = 0; i < total; i++) {
    await p.evaluate(t => window.seek(t), i / FPS);
    await p.screenshot({ path: `${DIR}/f${String(i).padStart(5,'0')}.jpg`, type: 'jpeg', quality: 94 });
    if (i % 120 === 0) process.stdout.write(`  ${i}/${total}\n`);
  }
  await b.close();
  console.log('Frames fertig:', total);
})();
