const { chromium } = require('playwright-core');
const F='/home/user/TennisSharpBot/instagram/reels/reel_01_gamma.html';
(async()=>{
  const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome'});
  const p=await b.newPage({viewport:{width:1080,height:1920}});
  await p.goto('file://'+F); await p.evaluate(()=>window.READY);
  const ts=[1.6,9.0,15.0,24.5,31.0];
  for(const t of ts){ await p.evaluate(v=>window.seek(v),t);
    await p.screenshot({path:`/tmp/f_${String(t).replace('.','_')}.png`}); }
  // Kontaktbogen
  await p.setViewportSize({width:1400,height:520});
  await p.setContent('<body style="margin:0;background:#05070A;display:flex;gap:14px;padding:14px">'+
    ts.map(t=>`<div style="text-align:center"><img src="file:///tmp/f_${String(t).replace('.','_')}.png" height="440">
    <div style="color:#8A96A8;font:14px sans-serif;margin-top:6px">${t}s</div></div>`).join('')+'</body>');
  await p.screenshot({path:'/tmp/preview.png'});
  await b.close();
})();
