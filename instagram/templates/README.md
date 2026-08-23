# Templates – Benutzung

## post_template.html
Im Browser öffnen. Drei fertige Slide-Typen im Markenlayout:
**Hook · Inhalt · Cheat-Sheet** (der Slide, der die Saves erzeugt).

**Als Bild exportieren (1080 × 1350):**
1. DevTools öffnen (F12) → im CSS `.slide { transform: scale(.5) }` auf `scale(1)` setzen
2. Rechtsklick auf das `<section class="slide">`-Element → *Node-Screenshot aufnehmen*

Alternativ per CLI mit Playwright (Chromium ist vorinstalliert):
```js
// screenshot.js  →  node screenshot.js
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 2 });
  await p.goto('file://' + __dirname + '/post_template.html');
  await p.addStyleTag({ content: '.slide{transform:none!important;margin:0!important}' });
  const slides = await p.$$('.slide');
  for (const [i, s] of slides.entries()) await s.screenshot({ path: `slide_${i + 1}.png` });
  await b.close();
})();
```

**Struktur nicht ändern, nur Text.** Der Wiedererkennungswert entsteht dadurch,
dass Kopfzeile, Fußzeile und Akzentbalken auf jedem Post exakt gleich sitzen.

## brand.json
Alle Design-Tokens an einer Stelle. Bei einem Rebrand nur hier ändern.

## hooks.md
60 einsatzfertige Hooks, nach Content-Säule sortiert.
Regel: Hook zuerst, Inhalt danach – nie umgekehrt.

## redaktionsplan.csv
Vier Wochen Startplan. In Sheets/Excel importieren und fortschreiben.
Spalten: Datum, Uhrzeit, Plattform, Säule, Format, Hook, CTA, Status.
