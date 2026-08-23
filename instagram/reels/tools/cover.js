const { chromium } = require('playwright-core');
(async()=>{const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome'});
const p=await b.newPage({viewport:{width:1080,height:1350}});
await p.goto('file:///home/user/TennisSharpBot/instagram/reels/cover_01_gamma.html');
await p.evaluate(()=>document.fonts.ready);
await p.screenshot({path:'/home/user/TennisSharpBot/instagram/reels/cover_01_gamma.png'});
await b.close()})();
