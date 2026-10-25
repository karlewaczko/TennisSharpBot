#!/usr/bin/env python3
"""Render data/processed/dashboard.json into a standalone HTML page.

    python scripts/build_dashboard.py && python scripts/render_dashboard.py

Kept separate from build_dashboard.py so the numbers can be regenerated
without touching the presentation and vice versa. The page is fully
self-contained (data inlined as JSON) -- it has no network access once
published, so nothing may be fetched at view time.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import html as html_mod
import json
from pathlib import Path

from tennissharp import config

HTML = """<title>Value Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root {
  --bg:#F6F8FA; --surface:#FFFFFF; --surface-2:#F0F3F7; --border:#DFE5EC;
  --text:#111820; --muted:#5B6672; --faint:#8A95A2;
  --accent:#1B6CA8; --accent-soft:#E4EFF8;
  --pos:#1A7A4C; --pos-soft:#E1F3E9;
  --warn:#9E6B14; --warn-soft:#FAF0DC;
  --neg:#A93B2C; --neg-soft:#FBE9E6;
  --shadow:0 1px 2px rgba(17,24,32,.05), 0 4px 16px rgba(17,24,32,.05);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg:#0D1218; --surface:#151B23; --surface-2:#1B222B; --border:#262F3A;
    --text:#E7ECF2; --muted:#8D99A7; --faint:#6B7684;
    --accent:#57A8DF; --accent-soft:#152A3A;
    --pos:#42C083; --pos-soft:#12291E;
    --warn:#D69B41; --warn-soft:#2B2313;
    --neg:#E27364; --neg-soft:#2E1917;
    --shadow:0 1px 2px rgba(0,0,0,.3), 0 4px 16px rgba(0,0,0,.25);
  }
}
:root[data-theme="dark"] {
  --bg:#0D1218; --surface:#151B23; --surface-2:#1B222B; --border:#262F3A;
  --text:#E7ECF2; --muted:#8D99A7; --faint:#6B7684;
  --accent:#57A8DF; --accent-soft:#152A3A;
  --pos:#42C083; --pos-soft:#12291E;
  --warn:#D69B41; --warn-soft:#2B2313;
  --neg:#E27364; --neg-soft:#2E1917;
  --shadow:0 1px 2px rgba(0,0,0,.3), 0 4px 16px rgba(0,0,0,.25);
}
* { box-sizing:border-box; }
body {
  margin:0; background:var(--bg); color:var(--text);
  font-family:"IBM Plex Sans",system-ui,-apple-system,sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
.wrap { max-width:1120px; margin:0 auto; padding:32px 20px 72px; }
.num { font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums; }
h1,h2,h3 { font-family:Archivo,system-ui,sans-serif; text-wrap:balance; margin:0; }

/* ---- header ---- */
header { display:flex; flex-wrap:wrap; gap:20px; align-items:flex-end;
         justify-content:space-between; padding-bottom:20px;
         border-bottom:2px solid var(--text); margin-bottom:24px; }
.brand { display:flex; align-items:center; gap:12px; }
.mark { width:34px; height:34px; flex:none; }
h1 { font-size:29px; font-weight:700; letter-spacing:-.02em; line-height:1.1; }
.sub { color:var(--muted); font-size:13.5px; margin-top:3px; }
.stamp { text-align:right; font-size:12px; color:var(--faint); line-height:1.7; }
.stamp b { color:var(--text); font-weight:600; }

/* ---- stat strip ---- */
.strip { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
         gap:1px; background:var(--border); border:1px solid var(--border);
         border-radius:10px; overflow:hidden; margin-bottom:26px; }
.stat { background:var(--surface); padding:14px 16px; }
.stat .k { font-size:10.5px; letter-spacing:.09em; text-transform:uppercase;
           color:var(--faint); font-weight:600; }
.stat .v { font-size:25px; font-weight:600; letter-spacing:-.02em; margin-top:2px;
           font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums; }
.stat .n { font-size:11.5px; color:var(--muted); }

/* ---- verdict banner ---- */
.verdict { display:flex; gap:14px; align-items:flex-start; padding:16px 18px;
           border-radius:10px; margin-bottom:28px; border:1px solid;
           background:var(--surface); border-color:var(--border); }
.verdict.none { background:var(--surface-2); }
.verdict.hit { background:var(--pos-soft); border-color:var(--pos); }
.verdict .icon { font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:19px;
                 line-height:1.3; color:var(--muted); flex:none; }
.verdict.hit .icon { color:var(--pos); }
.verdict h2 { font-size:15.5px; font-weight:600; }
.verdict p { margin:4px 0 0; font-size:13.5px; color:var(--muted); max-width:74ch; }

/* ---- section heads ---- */
.sec { display:flex; align-items:baseline; gap:12px; margin:34px 0 12px; }
.sec h2 { font-size:13px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; }
.sec .rule { flex:1; height:1px; background:var(--border); }
.sec .count { font-size:12px; color:var(--faint); font-family:"IBM Plex Mono",monospace; }

/* ---- match table ---- */
.tbl { border:1px solid var(--border); border-radius:10px; overflow:hidden;
       background:var(--surface); box-shadow:var(--shadow); }
.thead { display:grid; grid-template-columns:1fr 92px 92px 108px 84px;
         gap:10px; padding:9px 16px; background:var(--surface-2);
         border-bottom:1px solid var(--border);
         font-size:10.5px; letter-spacing:.07em; text-transform:uppercase;
         color:var(--faint); font-weight:600; }
.thead span:not(:first-child) { text-align:right; }
.row { border-bottom:1px solid var(--border); }
.row:last-child { border-bottom:0; }
.row > .side { display:grid; grid-template-columns:1fr 92px 92px 108px 84px;
               gap:10px; padding:11px 16px; align-items:center; }
.row > .side + .side { border-top:1px dashed var(--border); }
.side.fav { background:linear-gradient(90deg,var(--accent-soft),transparent 42%); }
.pname { font-weight:600; font-size:14.5px; letter-spacing:-.01em; }
.pmeta { font-size:11px; color:var(--faint); font-family:"IBM Plex Mono",monospace; }
.cell { text-align:right; font-family:"IBM Plex Mono",monospace;
        font-variant-numeric:tabular-nums; font-size:13.5px; }
.cell .lbl { display:none; }
.edge { font-weight:600; padding:2px 7px; border-radius:5px; display:inline-block; }
.edge.p { color:var(--pos); background:var(--pos-soft); }
.edge.n { color:var(--neg); background:var(--neg-soft); }
.edge.z { color:var(--muted); }

/* match meta bar */
.mhead { display:flex; flex-wrap:wrap; gap:8px 14px; align-items:center;
         padding:8px 16px; background:var(--surface-2);
         border-bottom:1px solid var(--border); font-size:11.5px; color:var(--muted); }
.tour { font-weight:600; color:var(--text); font-size:12px; }
.chip { font-size:10px; letter-spacing:.06em; text-transform:uppercase; font-weight:600;
        padding:2px 7px; border-radius:4px; background:var(--surface);
        border:1px solid var(--border); color:var(--muted); }
.chip.sharp { color:var(--accent); border-color:var(--accent); background:var(--accent-soft); }
.chip.day { text-transform:none; letter-spacing:.02em; color:var(--text);
            font-family:"IBM Plex Mono",monospace; }
.chip.stale { color:var(--warn); border-color:var(--warn); background:var(--warn-soft); }
.chip.quali { text-transform:none; letter-spacing:.02em; }

/* divergence bar: market vs model on one axis */
.bar { position:relative; height:6px; border-radius:3px; background:var(--surface-2);
       border:1px solid var(--border); margin-top:6px; overflow:hidden; }
.bar .mk { position:absolute; top:-1px; bottom:-1px; width:2px; background:var(--muted); }
.bar .md { position:absolute; top:-1px; bottom:-1px; width:2px; background:var(--accent); }
.bar .gap { position:absolute; top:-1px; bottom:-1px; background:var(--accent-soft); }

/* ---- how it works ---- */
.steps { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:14px; }
.step { background:var(--surface); border:1px solid var(--border); border-radius:9px;
        padding:14px 16px; }
.step .n { font-family:"IBM Plex Mono",monospace; font-size:11px; font-weight:600;
           color:var(--accent); letter-spacing:.05em; }
.step h3 { font-size:14px; font-weight:600; margin:3px 0 5px; }
.step p { margin:0; font-size:12.5px; color:var(--muted); line-height:1.5; }

/* ---- audit ---- */
.audit { background:var(--surface); border:1px solid var(--border);
         border-left:3px solid var(--warn); border-radius:9px; padding:18px 20px; }
.audit h2 { font-size:15px; font-weight:600; margin-bottom:8px; }
.audit p { margin:0 0 10px; font-size:13.5px; color:var(--muted); max-width:76ch; }
.audit dl { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
            gap:12px; margin:14px 0 0; }
.audit dt { font-size:10.5px; letter-spacing:.07em; text-transform:uppercase;
            color:var(--faint); font-weight:600; }
.audit dd { margin:1px 0 0; font-family:"IBM Plex Mono",monospace; font-size:17px;
            font-weight:600; font-variant-numeric:tabular-nums; }

/* ---- skipped ---- */
.skip { font-size:12.5px; color:var(--muted); }
.skip summary { cursor:pointer; font-weight:600; color:var(--text); padding:4px 0; }
.skip summary:focus-visible { outline:2px solid var(--accent); outline-offset:3px; border-radius:3px; }
.skip ul { margin:8px 0 0; padding-left:18px; columns:2; column-gap:28px; }
.skip li { margin-bottom:3px; break-inside:avoid; }

/* ---- forecast line + stats ---- */
.fcline { display:flex; flex-wrap:wrap; gap:6px 16px; padding:6px 16px; font-size:11.5px;
          color:var(--muted); border-bottom:1px solid var(--border); background:var(--surface); }
.fcline b { color:var(--text); font-weight:600; font-family:"IBM Plex Mono",monospace; }
.fcline .src { white-space:nowrap; }
.pstat { font-size:11px; color:var(--faint); font-family:"IBM Plex Mono",monospace; margin-top:2px; }

/* ---- price tables ---- */
.tblx { border:1px solid var(--border); border-radius:10px; overflow:auto;
        background:var(--surface); box-shadow:var(--shadow); }
.ptable { width:100%; border-collapse:collapse; font-size:13px; }
.ptable th { text-align:left; padding:9px 12px; background:var(--surface-2);
             border-bottom:1px solid var(--border); font-size:10.5px; letter-spacing:.07em;
             text-transform:uppercase; color:var(--faint); font-weight:600; white-space:nowrap; }
.ptable td { padding:8px 12px; border-bottom:1px solid var(--border); vertical-align:top; }
.ptable tr:last-child td { border-bottom:0; }
.ptable td.num, .ptable th.num { text-align:right; font-family:"IBM Plex Mono",monospace;
                                 font-variant-numeric:tabular-nums; white-space:nowrap; }
.ptable .m { font-weight:600; }
.ptable .s { color:var(--muted); font-size:11.5px; }
.chip.venue { text-transform:none; letter-spacing:.02em; }
.chip.pm { color:var(--warn); border-color:var(--warn); background:var(--warn-soft); text-transform:none; }
.note { margin:0 0 12px; font-size:13px; color:var(--muted); max-width:80ch; }
.board summary { cursor:pointer; font-weight:600; padding:6px 0; }
.board .line { font-size:12.5px; padding:6px 0; border-bottom:1px dashed var(--border); }
.board .line b { font-weight:600; }
.board .q { font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums; color:var(--muted); }

footer { margin-top:40px; padding-top:18px; border-top:1px solid var(--border);
         font-size:12px; color:var(--faint); }

/* ---- all matches ---- */
.am-legend { font-size:12.5px; line-height:1.55; color:var(--muted); margin:-2px 0 6px; }
.am-day { font-family:Archivo,sans-serif; font-size:17px; font-weight:600; margin:22px 0 10px;
          display:flex; flex-wrap:wrap; gap:4px 12px; align-items:baseline; }
.am-day .n, details.am-tn > summary .n { font-size:11.5px; font-weight:400; color:var(--faint);
          font-family:"IBM Plex Mono",monospace; }
details.am-tn { border:1px solid var(--border); border-radius:10px; background:var(--surface);
                box-shadow:var(--shadow); margin-bottom:8px; overflow:hidden; }
details.am-tn > summary { cursor:pointer; list-style:none; display:flex; flex-wrap:wrap;
                gap:6px 10px; align-items:center; padding:9px 14px; }
details.am-tn > summary::-webkit-details-marker { display:none; }
details.am-tn > summary::before { content:"▸"; color:var(--faint); font-size:11px; }
details.am-tn[open] > summary::before { content:"▾"; }
.am-p { display:grid; grid-template-columns:48px minmax(0,1fr) 50px 54px 46px 50px 56px 70px;
        gap:8px; align-items:center; padding:3px 14px; font-size:13px; }
.am-h { font-size:10px; letter-spacing:.07em; text-transform:uppercase; font-weight:600;
        color:var(--faint); background:var(--surface-2); border-top:1px solid var(--border);
        padding-top:6px; padding-bottom:6px; }
.am-p .num { text-align:right; font-family:"IBM Plex Mono",monospace;
             font-variant-numeric:tabular-nums; font-size:12.5px; }
.am-p .num.soft { color:var(--faint); }
.am-p .num.dev { color:var(--warn); font-weight:600; }
.am-p .t { font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--muted); }
.am-p .nm { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.am-p .meta { margin-left:8px; font-size:11px; color:var(--faint); font-family:"IBM Plex Mono",monospace; }
.am-p .edge { padding:1px 5px; }
.am-m { border-top:1px solid var(--border); padding:5px 0 6px; }
.am-m.sig { background:var(--pos-soft); }
.am-m.done, .am-m.live { opacity:.6; }
.am-note { padding:2px 14px 0 70px; font-size:12px; line-height:1.5; color:var(--muted); }
.am-note .pos, .am-p .pos { color:var(--pos); }
details.am-more { padding:2px 14px 0 70px; font-size:12px; }
details.am-more > summary { cursor:pointer; color:var(--accent); }
details.am-more p { margin:4px 0 2px; color:var(--muted); }
.am-cmp { border-collapse:collapse; margin-top:4px; }
.am-cmp th, .am-cmp td { padding:2px 14px 2px 0; text-align:right; font-size:11.5px;
                         font-family:"IBM Plex Mono",monospace; font-weight:400; }
.am-cmp th { color:var(--text); font-weight:600; font-family:inherit; }
.am-cmp td:first-child { text-align:left; color:var(--muted); font-family:inherit; }
.am-c { display:grid; grid-template-columns:48px minmax(0,1fr) 64px 92px minmax(0,170px);
        gap:8px; align-items:center; padding:5px 14px; font-size:13px; }
.am-c .num { text-align:right; font-family:"IBM Plex Mono",monospace; font-size:12.5px; }
.am-c .num.soft { color:var(--faint); }
.am-c .t { font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--muted); }
.am-c .nm, .am-c .st { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.am-c .st { font-size:11.5px; color:var(--muted); font-family:"IBM Plex Mono",monospace; }
.chip.sig { color:var(--pos); border-color:var(--pos); background:var(--pos-soft); }
.chip.live { color:var(--warn); border-color:var(--warn); background:var(--warn-soft); }
@media (max-width:720px) {
  .am-p { grid-template-columns:40px minmax(0,1fr) 38px 46px 58px; gap:6px; padding:3px 10px; }
  .am-p .x { display:none; }
  .am-c { grid-template-columns:40px minmax(0,1fr) 88px; gap:6px; padding:5px 10px; }
  .am-c > :nth-child(3) { display:none; }
  .am-c .st { grid-column:2 / -1; }
  .am-c .st:empty { display:none; }
  .am-p .nm { white-space:normal; }
  .am-p .meta { display:block; margin-left:0; }
  .am-note, details.am-more { padding-left:10px; padding-right:10px; }
}
@media (max-width:720px) {
  .thead { display:none; }
  .row > .side { grid-template-columns:1fr 1fr; gap:6px 10px; }
  .pname { grid-column:1/-1; }
  .cell { text-align:left; }
  .cell .lbl { display:block; font-size:9.5px; letter-spacing:.07em;
               text-transform:uppercase; color:var(--faint); font-family:"IBM Plex Sans",sans-serif; }
  .skip ul { columns:1; }
}
</style>

<div class="wrap">
  <header>
    <div class="brand">
      <svg class="mark" viewBox="0 0 40 40" aria-hidden="true">
        <circle cx="20" cy="20" r="17" fill="none" stroke="var(--accent)" stroke-width="2.5"/>
        <path d="M8 8c8 5 8 19 0 24M32 8c-8 5-8 19 0 24" fill="none"
              stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round"/>
      </svg>
      <div>
        <h1>Value Radar</h1>
        <div class="sub">Modell gegen Sharp-Markt &middot; Preisvergleich B&uuml;cher, Polymarket, Kalshi &middot; ATP, WTA, Challenger, ITF &middot; alle Partien heute &amp; morgen</div>
      </div>
    </div>
    <div class="stamp">
      Stand <b>__STAMP__</b><br>
      Schwelle <b>__THRESH__</b> EV &middot; Referenz bevorzugt Pinnacle
    </div>
  </header>

  <div class="strip">__STRIP__</div>

  __VERDICT__

  __ALLMATCHES__

  <div class="sec"><h2>Modellbewertung</h2><span class="rule"></span>
    <span class="count">__NMODEL__ Partien</span></div>
  <div class="tbl">
    <div class="thead">
      <span>Spieler</span><span>Prognose</span><span>Markt</span>
      <span>Faire Quote</span><span>EV bei Quote</span>
    </div>
    __ROWS__
  </div>

  __TAROWS__

  __FORECASTS__

  __SOFTVALUE__

  __PMBOARD__

  __PMPROS__

  __ARBS__

  __PRICEBOARD__

  <div class="verdict none" style="margin-top:26px">
    <div class="icon">&#8644;</div><div>
    <h2>Warum der Edge auf beiden Seiten gleich gro&szlig; ist</h2>
    <p><b>Edge</b> ist die Differenz Prognose minus Markt. Beide Prognosen ergeben zusammen
       100&nbsp;%, beide entvigten Marktwerte ebenfalls &mdash; die zwei Differenzen sind
       deshalb zwangsl&auml;ufig exakt spiegelbildlich. Das ist Rechenlogik, kein Fehler,
       aber es macht die Zahl f&uuml;r eine Wettentscheidung unbrauchbar.</p>
    <p><b>EV bei Quote</b> ist die Entscheidungsgr&ouml;&szlig;e: Prognose mal angebotene
       Quote minus 1. Weil die beiden Seiten unterschiedliche Quoten haben, ist sie
       <i>nicht</i> spiegelbildlich. Auf dieser Karte ist der Edge in
       <span class="num">__NMATCHES__ von __NMATCHES__</span> Partien symmetrisch, der EV in
       <span class="num">keiner einzigen</span>. Beispiel Ferro gegen Bennemann:
       Edge &plusmn;14,9&thinsp;%, EV aber &minus;18,9&thinsp;% gegen +91,1&thinsp;%.</p>
    </div></div>

  <div class="sec"><h2>Wie das Modell rechnet</h2><span class="rule"></span></div>
  <div class="steps">
    <div class="step"><div class="n">SCHRITT 1</div><h3>Sharp-Preis holen</h3>
      <p>Pinnacle bevorzugt, sonst das Buch mit der dünnsten Marge. Die angezeigte
         Referenz steht bei jeder Partie.</p></div>
    <div class="step"><div class="n">SCHRITT 2</div><h3>Marge herausrechnen</h3>
      <p>Shin-Devigging trennt den fairen Preis vom Aufschlag des Buchmachers.
         Ergebnis: die implizite Marktwahrscheinlichkeit.</p></div>
    <div class="step"><div class="n">SCHRITT 3</div><h3>Modell bewerten</h3>
      <p>Belags-Elo, Form, H2H, Ermüdung und Belagsgeschwindigkeit &mdash; mit dem
         fairen Marktpreis als zusätzlichem Merkmal. Daneben, unabhängig davon:
         Tennis Abstracts Elo und Turnierprognose sowie ein Punktmodell aus
         Aufschlag- und Returnquoten.</p></div>
    <div class="step"><div class="n">SCHRITT 4</div><h3>Differenz prüfen</h3>
      <p>Liegt die Modellwahrscheinlichkeit über der des Marktes, entsteht ein Edge.
         Ab __THRESH__ wird er markiert &mdash; entscheidend ist aber der EV zur Quote.</p></div>
  </div>

  <div class="sec"><h2>Was die Prüfung sagt</h2><span class="rule"></span></div>
  <div class="audit">
    <h2>Kein nachgewiesener Vorsprung gegenüber dem Markt</h2>
    <p>Dieses Dashboard zeigt, wo das Modell vom Markt abweicht &mdash; nicht, wo Geld zu
       verdienen ist. Die eigene Prüfung des Projekts (<span class="num">scripts/audit_edge.py</span>)
       trainiert je Saison ein Modell auf [Marktpreis] und eines auf [Marktpreis + unsere
       Merkmale]. Über <span class="num">__NTESTED__</span> Partien wird die Vorhersage durch
       unsere Merkmale nicht besser, sondern minimal schlechter.</p>
    <p>Der Backtest der 5&nbsp;%-Schwelle liefert <span class="num">__ROI__</span> ROI bei
       <span class="num">t&nbsp;=&nbsp;__T__</span> über <span class="num">__NBETS__</span> Wetten &mdash;
       statistisch nicht von null zu unterscheiden. Eine Abweichung hier ist ein Hinweis
       zum Nachschauen, kein Wettsignal.</p>
    <dl>
      <div><dt>Informationsgewinn</dt><dd>__GAIN__</dd></div>
      <div><dt>Geprüfte Partien</dt><dd>__NTESTED__</dd></div>
      <div><dt>Backtest ROI</dt><dd>__ROI__</dd></div>
      <div><dt>t-Statistik</dt><dd>__T__</dd></div>
    </dl>
  </div>

  __SKIPPED__

  <footer>
    Quoten und Spielplan von TennisExplorer, Elo-Referenz von Tennis Abstract, Prediction-Market-Preise von Polymarket (Gamma API) und Kalshi (Trade API), jeweils &ouml;ffentlich und ohne Schl&uuml;ssel gelesen.
    Erzeugt aus <span class="num">scripts/build_dashboard.py</span>; die Zahlen sind
    von der Kommandozeile reproduzierbar. Momentaufnahme, keine Anlageberatung.
  </footer>
</div>
"""


def pct(x, digits=1, sign=False):
    if x is None:
        return "&ndash;"
    return f"{x * 100:+.{digits}f}&thinsp;%" if sign else f"{x * 100:.{digits}f}&thinsp;%"


_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def day_chip(iso: str | None) -> str:
    """`2026-08-23` -> `So 23.08.`. A card now spans several playing days, so
    a row without its date reads as if every match were today's."""
    if not iso:
        return ""
    try:
        day = dt.date.fromisoformat(str(iso))
    except ValueError:
        return ""
    return (f'<span class="chip day">{_WEEKDAYS[day.weekday()]}&nbsp;'
            f'{day.day:02d}.{day.month:02d}.</span>')


def round_chip(match: dict) -> str:
    """Qualifying is a different event from the main draw -- different format
    for the men, and a field our own history barely covers. A row that does
    not say so reads as a main-draw match."""
    rnd = match.get("round")
    if not rnd:
        return ""
    cls = "chip quali" if match.get("is_qualifying") else "chip"
    return f'<span class="{cls}">{rnd}</span>'


def stale_chip(players) -> str:
    """Marks a row whose rest/form features describe a gap in our feed rather
    than the player. Such a row is never counted as a signal, but it still
    appears in the table, so it has to say why its numbers are soft."""
    if not players:
        return ""
    who = ", ".join(str(p) for p in players)
    return ('<span class="chip stale" title="Letztes Match in unserer Historie '
            f'zu lange her: {who}. Pause-, Form- und Ermuedungswerte beschreiben '
            'die Datenluecke, nicht den Spieler.">Daten veraltet</span>')


def esc(x) -> str:
    return html_mod.escape(str(x), quote=True)


def odds_fmt(x) -> str:
    return f"{x:.2f}" if isinstance(x, (int, float)) and x else "&ndash;"


def _match_cell(row: dict) -> str:
    a, b = row["players"]
    return (f'<div class="m">{esc(a)} &ndash; {esc(b)}</div>'
            f'<div class="s">{esc(row["tournament"])} {day_chip(row.get("date"))}'
            f'{" &middot; " + esc(row["round"]) if row.get("round") else ""}</div>')


def _table(headers, body_rows) -> str:
    head = "".join(f'<th class="{c}">{h}</th>' for h, c in headers)
    return f'<div class="tblx"><table class="ptable"><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table></div>'


def soft_value_section(data: dict) -> str:
    rows = data.get("soft_value") or []
    board = data.get("price_board") or []
    n_sharp = sum(1 for e in board if e.get("fair_quality", "sharp" if e.get("ref_is_sharp") else "soft") == "sharp")
    n_exch = sum(1 for e in board if e.get("fair_quality") == "exchange")
    intro = (f'<p class="note">Jede Quote jedes Buches auf der Match-Seite gegen den '
             f'<b>fairen Preis</b>: den entvigten Kurs des scharfen Buches (Pinnacle, sonst Betfair) '
             f'oder, wo keines quotiert, den Mittelkurs eines liquiden Prediction Markets '
             f'(mindestens 5&thinsp;000&nbsp;$ Tiefe, Spread höchstens 2 Cent). Positiv heißt: das weiche '
             f'Buch zahlt mehr, als der scharfe Markt die Seite wert hält &mdash; der klassische Weg, '
             f'auf dem Profis ohne eigenes Modell Geld verdienen, und der Grund, warum weiche Bücher '
             f'Gewinner limitieren. Basis: {n_sharp} Partien mit scharfem Buch, {n_exch} mit '
             f'Prediction-Market-Anker, von {len(board)} insgesamt.</p>')
    if not rows:
        body = ('<div class="verdict none"><div class="icon">&#9675;</div><div>'
                '<h2>Kein weiches Buch über dem Sharp-Fairwert</h2>'
                '<p>Normalfall: die weichen Bücher kopieren Pinnacle und legen ihre Marge obendrauf. '
                'Abweichungen entstehen kurz nach Nachrichten, wenn ein Buch noch nicht nachgezogen hat.</p>'
                '</div></div>')
    else:
        trs = []
        for r in rows[:20]:
            chip = "chip venue" if not r.get("signal_only") else "chip pm"
            note = " <span class=\"s\">(nur Signal)</span>" if r.get("signal_only") else ""
            trs.append(f'<tr><td>{_match_cell(r)}</td><td class="m">{esc(r["player"])}</td>'
                       f'<td><span class="{chip}">{esc(r["venue"])}</span>{note}</td>'
                       f'<td class="num">{odds_fmt(r["odds"])}</td>'
                       f'<td class="num">{odds_fmt(1 / r["fair_prob"]) if r["fair_prob"] else "&ndash;"}'
                       f' <span class="s">({esc(r.get("fair_source", r["ref_book"]))})</span></td>'
                       f'<td class="num"><span class="edge p">{pct(r["ev"], 1, sign=True)}</span></td></tr>')
        body = _table([("Partie", ""), ("Seite", ""), ("Buch", ""), ("Quote", "num"),
                       ("Faire Quote", "num"), ("EV", "num")], "".join(trs))
    return (f'<div class="sec"><h2>Sharp gegen Soft</h2><span class="rule"></span>'
            f'<span class="count">{len(rows)} Seiten im Plus</span></div>{intro}{body}')


def pm_section(data: dict) -> str:
    rows = data.get("pm_board") or []
    meta = data.get("prediction_markets") or {}
    status = meta.get("status") or {}
    venues = ", ".join(f'{v} {"&#10003;" if st.get("ok") else "&#10007;"} ({st.get("n_markets", 0)} Märkte)'
                       for v, st in status.items()) or "nicht abgefragt"
    intro = (f'<p class="note"><b>Nur Signal, kein Wettplatz:</b> Kalshi nimmt nur US-Kunden an, '
             f'Polymarket sperrt deutsche IPs und steht seit September 2025 auf der Sperrliste der GGL. '
             f'Die Preise sind trotzdem Information: ein liquider Markt, der von Pinnacle abweicht, '
             f'zeigt Geldfluss oder Nachrichten, die ein weiches Buch oft noch nicht eingepreist hat. '
             f'Quoten hier <b>netto</b> nach Taker-Gebühr (Polymarket 5&nbsp;%, Kalshi 7&nbsp;% '
             f'von p&middot;(1&minus;p) je Anteil). <b>EV Maker</b> unterstellt, dass eine eigene '
             f'Order zum aktuellen Bid gefüllt wird &mdash; eine Obergrenze, denn gefüllt wird sie '
             f'am ehesten, wenn der Markt gerade gegen sie läuft. '
             f'Abgefragt: {venues}; {meta.get("n_matched", 0)} Partien der Karte haben einen '
             f'Prediction-Market-Preis.</p>')
    shown = [r for r in rows if (r.get("ev") is not None and r["ev"] > 0)
             or (r.get("ev_maker") is not None and r["ev_maker"] > 0.02)
             or (r.get("mid_gap") is not None and abs(r["mid_gap"]) >= 0.02)]
    if not rows:
        body = ('<div class="verdict none"><div class="icon">&#9675;</div><div>'
                '<h2>Keine Partie mit Prediction-Market-Preis und scharfer Referenz</h2>'
                '<p>Entweder lief kein Markt oder keines der gelisteten Matches hat einen Pinnacle- '
                'oder Betfair-Preis auf TennisExplorer.</p></div></div>')
    elif not shown:
        body = ('<div class="verdict none"><div class="icon">&#9675;</div><div>'
                '<h2>Polymarket und Kalshi liegen auf dem Sharp-Markt</h2>'
                f'<p>Über {len(rows)} verglichene Seiten weicht kein Mittelkurs um zwei Punkte oder mehr '
                'vom Pinnacle-Fairwert ab, und nach Gebühr ist keine Seite im Plus.</p></div></div>')
    else:
        trs = []
        for r in shown[:20]:
            liq = f'{r["liquidity"]:,.0f}&nbsp;$'.replace(",", "&thinsp;") if r.get("liquidity") else "&ndash;"
            ev = r.get("ev"); evm = r.get("ev_maker"); gap = r.get("mid_gap")
            ecls = lambda v: "p" if v is not None and v > 0.005 else ("n" if v is not None and v < -0.005 else "z")
            trs.append(f'<tr><td>{_match_cell(r)}</td><td class="m">{esc(r["player"])}</td>'
                       f'<td><span class="chip pm">{esc(r["venue"])}</span></td>'
                       f'<td class="num">{r["bid"] if r.get("bid") is not None else "&ndash;"} / '
                       f'{r["ask"] if r.get("ask") is not None else "&ndash;"}</td>'
                       f'<td class="num">{odds_fmt(r.get("odds"))}</td>'
                       f'<td class="num">{pct(r["fair_prob"])}</td>'
                       f'<td class="num"><span class="edge {ecls(gap)}">{pct(gap, 1, sign=True) if gap is not None else "&ndash;"}</span></td>'
                       f'<td class="num"><span class="edge {ecls(ev)}">{pct(ev, 1, sign=True) if ev is not None else "&ndash;"}</span></td>'
                       f'<td class="num">{pct(evm, 1, sign=True) if evm is not None else "&ndash;"}</td>'
                       f'<td class="num">{liq}</td></tr>')
        body = _table([("Partie", ""), ("Seite", ""), ("Markt", ""), ("Bid / Ask", "num"),
                       ("Netto-Quote", "num"), ("Sharp fair", "num"), ("Mid &minus; fair", "num"),
                       ("EV Taker", "num"), ("EV Maker", "num"), ("Liquidität", "num")], "".join(trs))
    return (f'<div class="sec"><h2>Polymarket &amp; Kalshi gegen den Sharp-Markt</h2><span class="rule"></span>'
            f'<span class="count">{len(rows)} Seiten verglichen</span></div>{intro}{body}')


def _usd(x) -> str:
    try:
        return f"{float(x):,.0f}&nbsp;$".replace(",", "&thinsp;")
    except (TypeError, ValueError):
        return "&ndash;"


def _cents(x) -> str:
    try:
        return f"{float(x) * 100:+.1f}&thinsp;¢"
    except (TypeError, ValueError):
        return "&ndash;"


def _pro_link(name, wallet) -> str:
    """The profile's chosen name (or its short wallet when it kept the
    default), linked to its public Polymarket page."""
    w = str(wallet)
    name = name if isinstance(name, str) else ""
    if not name or (name.startswith("0x") and "-" in name):
        name = f"{w[:6]}…{w[-4:]}"
    return f'<a href="https://polymarket.com/profile/{esc(w)}" target="_blank" rel="noopener">{esc(name)}</a>'


def pm_pros_section(data: dict) -> str:
    """Polymarket's best-ranked tennis wallets and what they hold."""
    pros = data.get("pm_pros") or {}
    lb = pros.get("leaderboard") or []
    pos = pros.get("positions") or []
    sh = data.get("pm_sharpness") or {}
    cal = sh.get("polymarket_closing_calibration") or {}
    ms = sh.get("market_structure") or {}
    sp = sh.get("skill_persistence") or {}
    gaps = sh.get("gap_to_sharp") or {}
    facts = []
    for venue in ("Polymarket", "Kalshi"):
        g = gaps.get(venue)
        if g:
            facts.append(f'{venue}-Mittelkurs gegen den Pinnacle- oder Betfair-Fairwert: im Median '
                         f'{g["median_gap_pp"]:.1f} Prozentpunkte daneben, '
                         f'{g["share_within_1pp"] * 100:.0f}&thinsp;% der {g["sides"]} Seiten innerhalb eines Punktes.')
    if cal.get("n"):
        dev = max((abs(b["price"] - b["won"]) for b in cal.get("bins") or []), default=0)
        facts.append(f'Polymarkets letzter Kurs vor dem Start, {cal["n"]} entschiedene ATP- und WTA-Matches: '
                     f'Brier {cal["brier"]:.3f}, größte Abweichung zwischen Kurs und Siegquote in einem '
                     f'Preisband {dev * 100:.1f} Punkte.')
    if ms.get("stake_usd"):
        facts.append(f'Umsatz in {sh.get("window_days", 30)} Tagen: {ms["stake_usd"] / 1e6:.0f}&nbsp;Mio.&nbsp;$, '
                     f'davon {ms["in_play_share"] * 100:.0f}&thinsp;% während des Matches; die 20 größten '
                     f'Wallets bewegen {ms["top20_share"] * 100:.0f}&thinsp;%.')
    if sp.get("corr") is not None:
        facts.append(f'Hält der Vorsprung? Das beste Zehntel der ersten Monatshälfte schlug den Schlusskurs '
                     f'in der zweiten um {_cents(sp["top_decile_next"])}, der Schnitt lag bei '
                     f'{_cents(sp["all_next"])} (Korrelation {sp["corr"]:.2f} über {sp["wallets"]} Wallets): '
                     f'echtes, aber kleines Können.')
    intro = ('<p class="note"><b>Wie die Rangliste entsteht:</b> Jeder Polymarket-Trade ist öffentlich, mit '
             'Wallet und Profilnamen. Für jede Wallet wird über die entschiedenen ATP- und WTA-Matches des '
             'letzten Monats gemessen, ob ihre Käufe vor Spielbeginn den letzten Kurs vor dem Start '
             'geschlagen haben (Closing Line Value, CLV, in Cent je Anteil); sortiert nach der t-Statistik, '
             'damit ein paar Glückstreffer nicht oben landen. Aufgenommen werden nur Wallets mit mindestens '
             '20&nbsp;Matches und 2&thinsp;000&nbsp;$ Einsatz, die überwiegend vor dem Start und mit klarer '
             'Richtung setzen: Market Maker und Live-Bots halten Lagerbestand, keine Tipps. Kalshi '
             'veröffentlicht keine Trader-Daten.</p>'
             + (f'<p class="note">{" ".join(facts)}</p>' if facts else ""))
    if not lb:
        note = pros.get("note") or "keine Daten"
        return (f'<div class="sec"><h2>Profis auf Polymarket</h2><span class="rule"></span></div>'
                f'{intro}<p class="note">Rangliste: {esc(note)}.</p>')
    trs = []
    for r in lb:
        trs.append(f'<tr><td class="num">{int(r["rank"])}</td><td class="m">{_pro_link(r.get("name"), r["wallet"])}</td>'
                   f'<td class="num">{int(r["pre_markets"])}</td><td class="num">{_usd(r["stake"])}</td>'
                   f'<td class="num">{_usd(r["pnl"])}</td>'
                   f'<td class="num">{pct(r.get("roi"), 1, sign=True)}</td>'
                   f'<td class="num">{_cents(r.get("clv_mean"))}</td>'
                   f'<td class="num">{float(r["clv_t"]):.1f}</td>'
                   f'<td class="num">{pct(r.get("live_share"), 0)}</td></tr>')
    table = _table([("#", "num"), ("Profil", ""), ("Matches vor Start", "num"), ("Einsatz", "num"),
                    ("Gewinn", "num"), ("ROI", "num"), ("CLV &Oslash;", "num"), ("t", "num"),
                    ("Live-Anteil", "num")], "".join(trs))
    on_card = [p for p in pos if p.get("match_id")]
    if on_card:
        prs = []
        for p in on_card[:25]:
            ev = p.get("ev_best")
            ecls = "p" if ev is not None and ev > 0.005 else ("n" if ev is not None and ev < -0.005 else "z")
            prs.append(f'<tr><td>{_match_cell({"players": p["players"], "tournament": p["tournament"], "date": p.get("date")})}</td>'
                       f'<td>{_pro_link(p.get("name"), p["wallet"])} <span class="s">#{int(p["rank"])}</span></td>'
                       f'<td class="m">{esc(p["side"])}</td>'
                       f'<td class="num">{p["avg_price"]:.2f} &rarr; {p["cur_price"]:.2f}</td>'
                       f'<td class="num">{_usd(p.get("initial_value"))}</td>'
                       f'<td class="num">{pct(p.get("fair"))} <span class="s">{esc(p.get("fair_source") or "")}</span></td>'
                       f'<td class="num">{odds_fmt(p.get("best_odds"))} <span class="s">{esc(p.get("best_book") or "")}</span></td>'
                       f'<td class="num"><span class="edge {ecls}">{pct(ev, 1, sign=True) if ev is not None else "&ndash;"}</span></td></tr>')
        ptable = _table([("Partie", ""), ("Profil", ""), ("Seite", ""), ("Einstieg &rarr; jetzt", "num"),
                         ("Einsatz", "num"), ("Fair", "num"), ("Beste Buchquote", "num"), ("EV", "num")],
                        "".join(prs))
        pos_html = (f'<p class="note" style="margin-top:14px">Offene Positionen der Top-{PRO_SHOWN} auf Partien '
                    f'dieser Karte. EV ist die beste Buchquote gegen den fairen Preis, nicht gegen die '
                    f'Meinung des Profils.</p>{ptable}')
    else:
        pos_html = (f'<p class="note" style="margin-top:14px">Keines der Top-{PRO_SHOWN}-Profile hält gerade eine '
                    f'Position auf einer Partie dieser Karte ({len(pos)} offene Tennis-Positionen insgesamt).</p>')
    total = sh.get("ranked_wallets") or len(lb)
    return (f'<div class="sec"><h2>Profis auf Polymarket</h2><span class="rule"></span>'
            f'<span class="count">Top {len(lb)} von {total}, {len(on_card)} Positionen auf der Karte</span></div>'
            f'{intro}{table}{pos_html}')


PRO_SHOWN = 20


def arb_section(data: dict) -> str:
    arbs = data.get("arbs") or []
    near = data.get("near_arbs") or []
    board = data.get("price_board") or []
    intro = ('<p class="note">Beste Quote je Seite über alle Bücher und beide Prediction Markets '
             '(dort netto nach Gebühr). Ergibt 1/Q<sub>A</sub>&nbsp;+&nbsp;1/Q<sub>B</sub> weniger als 1, '
             'ist das Paar eine Arbitrage. Paare mit einem Bein bei Polymarket, Kalshi oder Betfair sind '
             'aus Deutschland nicht spielbar und entsprechend markiert.</p>')

    def leg(side):
        chip = "chip pm" if side.get("signal_only") else "chip venue"
        return (f'<div class="m">{esc(side["player"])}</div><div><span class="{chip}">{esc(side["venue"])}</span> '
                f'<span class="q">{odds_fmt(side["odds"])}</span></div>')

    def rows_for(items, cls):
        trs = []
        for r in items[:12]:
            trs.append(f'<tr><td>{_match_cell(r)}</td><td>{leg(r["side_a"])}</td><td>{leg(r["side_b"])}</td>'
                       f'<td class="num"><span class="edge {cls}">{pct(r["margin"], 2, sign=True)}</span></td>'
                       f'<td class="num">{pct(r["profit"], 2, sign=True)}</td>'
                       f'<td class="num">{r["stake_a"] * 100:.0f} / {r["stake_b"] * 100:.0f}</td>'
                       f'<td>{"nur Signal" if r.get("signal_only") else "spielbar"}</td></tr>')
        return _table([("Partie", ""), ("Seite A", ""), ("Seite B", ""), ("Summe &minus; 1", "num"),
                       ("Gewinn", "num"), ("Einsatz A / B %", "num"), ("Status", "")], "".join(trs))

    if arbs:
        body = rows_for(arbs, "p")
    else:
        body = ('<div class="verdict none"><div class="icon">&#9675;</div><div>'
                '<h2>Keine Arbitrage auf dieser Karte</h2>'
                f'<p>Über {len(board)} Partien summiert kein bestes Quotenpaar unter 1. Das ist der Normalfall: '
                'Arbitragen zwischen Büchern leben Minuten, nicht Stunden, und werden von Scannern mit '
                'Sekundentakt abgeräumt.</p></div></div>')
        if near:
            body += ('<p class="note" style="margin-top:12px">Knappste Paare (Summe unter 1,01):</p>'
                     + rows_for(near, "z"))
    return (f'<div class="sec"><h2>Arbitrage</h2><span class="rule"></span>'
            f'<span class="count">{len(arbs)} gefunden</span></div>{intro}{body}')


def price_board_section(data: dict) -> str:
    board = data.get("price_board") or []
    if not board:
        return ""
    lines = []
    for e in sorted(board, key=lambda x: (x.get("date") or "", x["circuit"], x["tournament"])):
        a, b = e["players"]
        parts = []
        for book, q in sorted(e["books"].items(), key=lambda kv: (kv[0] not in ("Pinnacle", "Betfair"), kv[0])):
            mark = "<b>" if book == e["ref_book"] else ""
            end = "</b>" if book == e["ref_book"] else ""
            parts.append(f'{mark}{esc(book)}{end} <span class="q">{odds_fmt(q[0])}/{odds_fmt(q[1])}</span>')
        for q in e.get("prediction_markets") or []:
            t = q["taker_odds"]
            parts.append(f'<span class="chip pm">{esc(q["venue"])}</span> '
                         f'<span class="q">{odds_fmt(t[0])}/{odds_fmt(t[1])}</span>')
        lines.append(f'<div class="line"><b>{esc(a)} &ndash; {esc(b)}</b> '
                     f'<span class="s">{esc(e["tournament"])} &middot; {esc(e["circuit"])}</span> '
                     f'{day_chip(e.get("date"))}<br>{" &middot; ".join(parts)}</div>')
    return (f'<div class="sec"><h2>Alle Preise</h2><span class="rule"></span>'
            f'<span class="count">{len(board)} Partien</span></div>'
            f'<details class="board"><summary>Jede Partie mit jedem Buch (Referenz fett, '
            f'Prediction Markets netto)</summary>{"".join(lines)}</details>')


def _p(x, digits=0) -> str:
    return pct(x, digits) if x is not None else "&ndash;"


def forecast_line(match: dict) -> str:
    """Every source's probability for the first-named player on one line:
    market, model, Tennis Abstract Elo, Tennis Abstract's tournament
    forecast, the serve/return point model."""
    a = match["sides"][0]
    parts = [f'<span class="src">Markt <b>{_p(a.get("market_prob"))}</b></span>']
    if match.get("method") == "model":
        parts.append(f'<span class="src">Modell <b>{_p(a.get("model_prob"))}</b></span>')
    ta = match.get("ta")
    if ta:
        basis = "Belag-Elo" if ta.get("basis") == "surface" else "Elo"
        parts.append(f'<span class="src">TA-{basis} <b>{_p(ta["prob_1"])}</b></span>')
    fc = match.get("ta_forecast")
    if fc:
        h2h = fc.get("h2h") or [None, None]
        h2h_txt = f' &middot; H2H {h2h[0]}:{h2h[1]}' if h2h[0] is not None else ""
        parts.append(f'<span class="src">TA-Forecast <b>{_p(fc["prob_1"])}</b>{h2h_txt}</span>')
    st = match.get("stats")
    if st and st.get("prob_1") is not None:
        parts.append(f'<span class="src">Statistik-Modell <b>{_p(st["prob_1"])}</b></span>')
    if len(parts) <= 1:
        return ""
    return f'<div class="fcline"><span class="src" style="color:var(--faint)">f&uuml;r {esc(a["player"])}:</span>{"".join(parts)}</div>'


def side_stats(match: dict, idx: int) -> str:
    """Tennis Abstract Elo and the last-52-week serve/return profile of one side."""
    bits = []
    ta = match.get("ta")
    if ta:
        t = ta["sides"][idx]
        elo = f'TA-Elo {t["elo"]:.0f}' if t.get("elo") else ""
        if t.get("surface_elo"):
            elo += f' &middot; {esc(t.get("surface") or "Belag")} {t["surface_elo"]:.0f}'
        if t.get("official_rank"):
            elo += f' &middot; Rang {t["official_rank"]:.0f}'
        if t.get("age"):
            elo += f' &middot; {t["age"]:.0f}&nbsp;J.'
        bits.append(elo)
    st = match.get("stats")
    if st:
        p = st["sides"][idx]
        scope = esc(p.get("scope") or "")
        line = []
        if p.get("spw") is not None:
            line.append(f'Aufschlag {p["spw"] * 100:.0f}&thinsp;%')
        if p.get("rpw") is not None:
            line.append(f'Return {p["rpw"] * 100:.0f}&thinsp;%')
        if p.get("hold_pct") is not None:
            line.append(f'Hold {p["hold_pct"] * 100:.0f}&thinsp;%')
        if p.get("break_pct") is not None:
            line.append(f'Break {p["break_pct"] * 100:.0f}&thinsp;%')
        if p.get("ace_pct") is not None:
            line.append(f'Ass {p["ace_pct"] * 100:.1f}&thinsp;%')
        if p.get("form10"):
            line.append(f'Form {esc(p["form10"])}')
        n = p.get("matches")
        bits.append(" &middot; ".join(line) + (f' <span title="{scope}, letzte 52 Wochen">({n} Matches {scope})</span>' if n else ""))
    if not bits:
        return ""
    return '<div class="pstat">' + "<br>".join(bits) + "</div>"


def forecast_section(data: dict) -> str:
    """One table: every scored match, every source, sorted by how far the
    farthest source sits from the market."""
    rows = []
    for m in data.get("matches") or []:
        a = m["sides"][0]
        mk = a.get("market_prob")
        if mk is None:
            continue
        srcs = {"model": a.get("model_prob") if m.get("method") == "model" else None,
                "ta": (m.get("ta") or {}).get("prob_1"),
                "fc": (m.get("ta_forecast") or {}).get("prob_1"),
                "st": (m.get("stats") or {}).get("prob_1")}
        if not any(v is not None for v in srcs.values()):
            continue
        devs = [abs(v - mk) for v in srcs.values() if v is not None]
        rows.append((max(devs), m, mk, srcs))
    if not rows:
        return ""
    rows.sort(key=lambda r: r[0], reverse=True)

    def cell(v, mk):
        if v is None:
            return '<td class="num">&ndash;</td>'
        d = v - mk
        cls = "p" if d > 0.03 else ("n" if d < -0.03 else "z")
        return f'<td class="num">{pct(v, 0)} <span class="edge {cls}" style="font-size:11px">{pct(d, 1, sign=True)}</span></td>'

    trs = []
    for dev, m, mk, srcs in rows:
        trs.append(f'<tr><td>{_match_cell({"players": [m["sides"][0]["player"], m["sides"][1]["player"]], "tournament": m["tournament"], "date": m.get("date"), "round": m.get("round")})}</td>'
                   f'<td class="num">{pct(mk, 0)} <span class="s">{esc(m.get("fair_source") or m["ref_book"])}</span></td>'
                   f'{cell(srcs["model"], mk)}{cell(srcs["ta"], mk)}{cell(srcs["fc"], mk)}{cell(srcs["st"], mk)}</tr>')
    src = data.get("sources") or {}
    intro = (f'<p class="note">Wahrscheinlichkeit des erstgenannten Spielers aus jeder Quelle, daneben die '
             f'Abweichung vom fairen Marktpreis. <b>Modell</b>: unser Klassifikator mit Marktpreis als Merkmal. '
             f'<b>TA-Elo</b>: Tennis Abstracts Elo, belagsspezifisch wo vorhanden, durch die Elo-Formel. '
             f'<b>TA-Forecast</b>: Tennis Abstracts eigene Turnierprognose von der Seite des laufenden Turniers. '
             f'<b>Statistik</b>: Barnett-Clarke-Punktmodell aus Aufschlag- und Returnquoten der letzten 52 Wochen '
             f'(TennisMyLife, Sackmann-Schema). Eine Abweichung ist kein Edge: gegen einen auf 0,8 Punkte '
             f'kalibrierten Markt ist sie fast immer der Fehler der Quelle. Jede Zeile wird in '
             f'<span class="num">forecasts_log.csv</span> festgehalten, damit die Quellen an den Ergebnissen '
             f'gemessen werden k&ouml;nnen. Abgedeckt: TA-Elo {src.get("ta_elo", 0)}, TA-Forecast '
             f'{src.get("ta_forecast", 0)}, Statistik {src.get("stats", 0)} Partien.</p>')
    table = _table([("Partie", ""), ("Markt", "num"), ("Modell", "num"), ("TA-Elo", "num"),
                    ("TA-Forecast", "num"), ("Statistik", "num")], "".join(trs))
    return (f'<div class="sec"><h2>Prognosevergleich</h2><span class="rule"></span>'
            f'<span class="count">{len(rows)} Partien</span></div>{intro}{table}')


def fair_chip(match: dict) -> str:
    """Names the fair value's source when it is not the quoted book: a
    liquid Polymarket or Kalshi mid stands in for a missing sharp price."""
    src = match.get("fair_source")
    if not src or src == match.get("ref_book"):
        return ""
    return (f'<span class="chip pm" title="Fairwert aus dem Mittelkurs eines liquiden '
            f'Prediction Markets; die Quote daneben ist der Preis des genannten Buches">'
            f'Fair: {esc(src)}</span>')


# ------------------------------------------------------------ every match ----

_DAYS_LONG = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
_MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember")
_SURFACE_DE = {"hard": "Hart", "clay": "Sand", "grass": "Rasen", "carpet": "Teppich"}
# Collapsed by default: ITF, UTR and the "Futures" band fill most of the
# list and rarely carry anything but a quote.
_OPEN_CATS = ("ATP", "WTA", "Challenger")
# A pure rating this far from the market is worth a line in the analysis.
_GAP_NOTE = 0.10


def _pp(x) -> str:
    return f"{x * 100:.0f}" if x is not None else "&ndash;"


def _join(words) -> str:
    words = list(words)
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " und " + words[-1]


def _am_meta(prof: dict | None) -> str:
    if not prof:
        return '<span class="meta">kein Profil</span>'
    bits = []
    if prof.get("rank"):
        bits.append(f'#{prof["rank"]:.0f}')
    if prof.get("elo"):
        selo = f' ({prof["selo"]:.0f})' if prof.get("selo") else ""
        bits.append(f'Elo {prof["elo"]:.0f}{selo}')
    if prof.get("form"):
        bits.append(f'Form {esc(prof["form"])}')
    return f'<span class="meta">{" &middot; ".join(bits)}</span>'


def _am_note(m: dict, thresh: str) -> str:
    """One or two sentences a bettor can act on: the signal if there is one,
    else who the market favours, whether the market-free opinions agree, and
    what BetInAsia's price is worth against the model."""
    a, b = m["players"]
    if m["status"] == "finished":
        return f'Beendet{": " + esc(m["score"]) if m.get("score") else ""}.'
    if m["status"] == "live":
        return ('L&auml;uft' + (f': {esc(m["score"])}' if m.get("score") else "")
                + ' &mdash; die Vorab-Analyse gilt nicht mehr.')
    sig = m.get("signal")
    if sig:
        return (f'<b class="pos">Signal:</b> {esc(m["players"][sig["side"]])} bei {sig["book"]} '
                f'(BetInAsia) zu {sig["odds"]:.2f}, EV {pct(sig["ev"], 1, sign=True)} gegen das '
                f'Modell. Vor der Wette den aktuellen Preis bei BetInAsia pr&uuml;fen.')
    fair = m.get("fair")
    if not fair:
        return 'Keine belastbare Quote &mdash; keine Bewertung.'
    fav = 0 if fair[0] >= fair[1] else 1
    parts = [f'Favorit laut Markt: <b>{esc(m["players"][fav])}</b> ({_pp(fair[fav])}&thinsp;%).']
    have = {k: v for k, v in (("Modell", m.get("model")), ("Elo", m.get("elo")),
                              ("Statistik", m.get("stat"))) if v is not None}
    against = [k for k, v in have.items() if (v >= 0.5) != (fav == 0)]
    agree = [k for k in have if k not in against]
    if against:
        parts.append(f'{_join(against)} {"sieht" if len(against) == 1 else "sehen"} '
                     f'{esc(m["players"][1 - fav])} vorn.')
    elif agree:
        parts.append(f'{_join(agree)} {"stimmt" if len(agree) == 1 else "stimmen"} zu.')
    gaps = [(k, v - fair[0]) for k, v in have.items() if k != "Modell"]
    if gaps:
        k, g = max(gaps, key=lambda t: abs(t[1]))
        if abs(g) >= _GAP_NOTE:
            parts.append(f'{k} gibt {esc(a if g > 0 else b)} {abs(g) * 100:.0f} Punkte mehr als '
                         f'der Markt &mdash; Hinweis, kein Signal.')
    ev = m.get("ev_bia")
    if ev:
        k = 0 if ev[0] >= ev[1] else 1
        parts.append(f'Bestes EV bei BetInAsia: {pct(ev[k], 1, sign=True)} '
                     f'({esc(m["players"][k])} zu {m["pinnacle"][k]:.2f}), Schwelle {thresh}.')
    elif m.get("model") is not None:
        parts.append('Pinnacle quotiert noch nicht &mdash; kein BetInAsia-Preis zum Pr&uuml;fen.')
    elif m.get("pinnacle"):
        parts.append('Pinnacle-Preis da, aber kein Modellwert &mdash; kein Signal m&ouml;glich.')
    elif not any(m.get("profiles") or []):
        parts.append('Keine Spielerdaten, kein Modell, kein Pinnacle-Preis.')
    else:
        parts.append('Kein Modellwert, kein Pinnacle-Preis.')
    if m.get("stale"):
        parts.append(f'Daten veraltet: {esc(", ".join(m["stale"]))}.')
    soft = m.get("soft")
    if soft:
        parts.append(f'{esc(soft["book"])} zahlt {soft["odds"]:.2f} auf '
                     f'{esc(m["players"][soft["side"]])} ({pct(soft["ev"], 1, sign=True)} gegen '
                     f'fair) &mdash; nicht bei BetInAsia.')
    return " ".join(parts)


def _am_details(m: dict) -> str:
    profs = m.get("profiles") or []
    if not any(profs):
        return ""
    profs = (profs + [None, None])[:2]

    def cell(prof, fn):
        try:
            return fn(prof) if prof else "&ndash;"
        except (KeyError, TypeError):
            return "&ndash;"

    surf = _SURFACE_DE.get(str(m.get("surface") or "").lower())
    lines = [
        ("Weltrangliste", lambda p: f'#{p["rank"]:.0f}'),
        ("Elo (Rang)", lambda p: f'{p["elo"]:.0f} ({p["elo_rank"]:.0f})'),
        (f"Elo {surf}" if surf else "Belag-Elo", lambda p: f'{p["selo"]:.0f}'),
        ("yElo 2026", lambda p: f'{p["yelo"]:.0f}'),
        ("Bilanz 52 Wochen", lambda p: f'{p["w"]:.0f}-{p["l"]:.0f}'
                                       + (f' ({_SURFACE_DE.get(p["scope"], p["scope"])})'
                                          if p.get("scope") else "")),
        ("Form (letzte 10)", lambda p: esc(p["form"])),
        ("Aufschlagpunkte", lambda p: pct(p["spw"], 1)),
        ("Returnpunkte", lambda p: pct(p["rpw"], 1)),
        ("Hold / Break", lambda p: f'{p["hold"] * 100:.0f} / {p["brk"] * 100:.0f}&thinsp;%'),
        ("Letztes Match", lambda p: esc(p["last"])),
        ("Alter", lambda p: f'{p["age"]:.1f}'.replace(".", ",")),
    ]
    body = "".join(f'<tr><td>{lbl}</td><td>{cell(profs[0], fn)}</td><td>{cell(profs[1], fn)}</td></tr>'
                   for lbl, fn in lines)
    head = (f'<tr><th></th><th>{esc(m["players"][0])}</th><th>{esc(m["players"][1])}</th></tr>')
    extra = []
    if m.get("h2h"):
        extra.append(f'H2H (52 Wochen) {m["h2h"][0]}:{m["h2h"][1]}')
    if m.get("ta_forecast") is not None:
        extra.append(f'TA-Turnierprognose {_pp(m["ta_forecast"])}&thinsp;% f&uuml;r {esc(m["players"][0])}')
    if m.get("fair_source"):
        extra.append(f'Markt aus {esc(m["fair_source"])}')
    if m.get("best"):
        extra.append("Beste Quote " + " / ".join(f'{esc(bk)} {o:.2f}' for bk, o in m["best"]))
    return (f'<details class="am-more"><summary>Spielerprofile</summary>'
            f'<table class="am-cmp">{head}{body}</table>'
            f'{"<p>" + " &middot; ".join(extra) + "</p>" if extra else ""}</details>')


def _is_rich(m: dict) -> bool:
    """An upcoming match with anything beyond a quote gets the full block;
    the rest -- no profile, model or Pinnacle price, or already under way --
    one line."""
    return m["status"] == "upcoming" and bool(
        any(m.get("profiles") or []) or m.get("model") is not None or m.get("pinnacle"))


def _am_line(m: dict) -> str:
    fair, best, odds = m.get("fair"), m.get("best"), m.get("odds")
    names = [esc(n) for n in m["players"]]
    if fair:
        fav = 0 if fair[0] >= fair[1] else 1
        names[fav] = f"<b>{names[fav]}</b>"
    price = [best[0][1], best[1][1]] if best else odds
    tail = {"finished": esc(m.get("score") or "beendet"),
            "live": '<span class="chip live">live</span> ' + esc(m.get("score") or "")}.get(m["status"], "")
    cls = "am-m am-c" + {"live": " live", "finished": " done"}.get(m["status"], "")
    return (f'<div class="{cls}"><span class="t">{m.get("time") or "&ndash;"}</span>'
            f'<span class="nm">{names[0]} &ndash; {names[1]}</span>'
            f'<span class="num">{_pp(fair[0]) + " / " + _pp(fair[1]) if fair else "&ndash;"}</span>'
            f'<span class="num soft">{odds_fmt(price[0]) + " / " + odds_fmt(price[1]) if price else "&ndash;"}</span>'
            f'<span class="st">{tail}</span></div>')


_RICH_HEAD = ('<div class="am-p am-h"><span>Zeit</span><span>Spieler</span><span class="num">Markt</span>'
              '<span class="num x">Modell</span><span class="num x">Elo</span>'
              '<span class="num x">Stat.</span><span class="num">Quote</span>'
              '<span class="num">EV BiA</span></div>')
_FLAT_HEAD = ('<div class="am-c am-h"><span>Zeit</span><span>Partie</span><span class="num">Markt</span>'
              '<span class="num">Quote</span><span>Stand</span></div>')
_STATUS_ORDER = {"upcoming": 0, "live": 1, "finished": 2}


def _am_match(m: dict, thresh: str) -> str:
    fair, pin, best, odds = m.get("fair"), m.get("pinnacle"), m.get("best"), m.get("odds")
    ev = m.get("ev_bia")
    profs = ((m.get("profiles") or []) + [None, None])[:2]
    fav = (0 if fair[0] >= fair[1] else 1) if fair else None
    sig = m.get("signal")
    status_word = {"live": '<span class="chip live">live</span>', "finished": "Ende"}.get(m["status"], "")
    lines = []
    for i in (0, 1):
        def side(p):
            return None if p is None else (p if i == 0 else 1 - p)

        def gap_cls(p):
            mk = side(fair[0]) if fair else None
            return " dev" if p is not None and mk is not None and abs(side(p) - mk) >= _GAP_NOTE else ""

        if pin:
            price, src, cls = pin[i], "Pinnacle (BetInAsia)", "num"
        elif best:
            price, src, cls = best[i][1], f"{best[i][0]} (nicht BetInAsia)", "num soft"
        else:
            price, src, cls = (odds[i] if odds else None), "Spielplan-Quote", "num soft"
        ev_i = ev[i] if ev else None
        ecls = "p" if ev_i is not None and ev_i > 0.005 else ("n" if ev_i is not None and ev_i < -0.005 else "z")
        ev_html = f'<span class="edge {ecls}">{pct(ev_i, 1, sign=True)}</span>' if ev_i is not None else "&ndash;"
        name = esc(m["players"][i])
        if sig and sig["side"] == i:
            name = f'<b class="pos">&#9650; {name}</b>'
        elif fav == i:
            name = f"<b>{name}</b>"
        lines.append(
            f'<div class="am-p">'
            f'<span class="t">{(m.get("time") or "&ndash;") if i == 0 else status_word}</span>'
            f'<span class="nm">{name}{_am_meta(profs[i])}</span>'
            f'<span class="num">{_pp(side(fair[0])) if fair else "&ndash;"}</span>'
            f'<span class="num x">{_pp(side(m.get("model")))}</span>'
            f'<span class="num x{gap_cls(m.get("elo"))}">{_pp(side(m.get("elo")))}</span>'
            f'<span class="num x{gap_cls(m.get("stat"))}">{_pp(side(m.get("stat")))}</span>'
            f'<span class="{cls}" title="{src}">{odds_fmt(price)}</span>'
            f'<span class="num">{ev_html}</span></div>')
    cls = "am-m" + (" sig" if sig else "") + {"live": " live", "finished": " done"}.get(m["status"], "")
    return (f'<div class="{cls}">{"".join(lines)}'
            f'<div class="am-note">{_am_note(m, thresh)}</div>{_am_details(m)}</div>')


def all_matches_section(data: dict) -> str:
    board = data.get("all_matches")
    if not board or not board.get("days"):
        return ""
    thresh = pct(board.get("threshold", data["threshold"]), 0)
    books = " / ".join(board.get("books") or ["Pinnacle"])
    out = [
        f'<div class="sec" id="alle-partien"><h2>Alle Partien &middot; heute &amp; morgen</h2>'
        f'<span class="rule"></span><span class="count">{len(board["matches"])} Partien</span></div>',
        f'<p class="am-legend">Zeiten in deutscher Zeit, Wahrscheinlichkeiten in Prozent f&uuml;r den '
        f'jeweiligen Spieler. <b>Markt</b> = fairer Preis ohne Marge (Pinnacle, sonst Betfair oder '
        f'liquider Polymarket/Kalshi-Mittelkurs, sonst die Spielplan-Quote). <b>Modell</b> = '
        f'trainiertes Modell mit Marktpreis, <b>Elo</b> = Tennis-Abstract-Elo (Belag, wo bekannt), '
        f'<b>Stat.</b> = Punktmodell aus Aufschlag und Return der letzten 52 Wochen. <b>Quote</b>: '
        f'schwarz = {books}, bei BetInAsia spielbar; grau = anderes Buch oder Spielplan-Quote. '
        f'Partien ohne Spielerdaten, Modell und Pinnacle-Preis sowie laufende und beendete stehen '
        f'einzeilig. <b>Signal</b> nur ab {thresh} EV des Modells zum {books}-Preis. Elo- und '
        f'Statistik-Abweichungen sind Hinweise, keine Signale: Beide kennen den Markt nicht, und '
        f'der Markt liegt im Mittel n&auml;her an den Ergebnissen.</p>',
    ]
    for k, day in enumerate(board["days"]):
        d = dt.date.fromisoformat(day["date"])
        label = ("Heute", "Morgen")[k] + " &middot; " if k < 2 else ""
        out.append(
            f'<h3 class="am-day">{label}{_DAYS_LONG[d.weekday()]}, {d.day}. {_MONTHS[d.month - 1]}'
            f'<span class="n">{day["n"]} Partien &middot; {day["n_upcoming"]} offen &middot; '
            f'{day["n_profiled"]} mit Spielerprofil &middot; {day["n_model"]} mit Modell &middot; '
            f'{day["n_pinnacle"]} mit Pinnacle &middot; {day["n_signals"]} Signal(e)</span></h3>')
        groups: dict = {}
        for m in board["matches"]:
            if m["day"] == day["date"]:
                groups.setdefault((m["cat"], m["tournament"]), []).append(m)
        if not groups:
            out.append('<p class="am-legend">Noch kein Spielplan ver&ouml;ffentlicht &mdash; '
                       'der n&auml;chste Lauf liest ihn neu.</p>')
        for (cat, tn), ms in groups.items():
            n_open = sum(m["status"] == "upcoming" for m in ms)
            n_sig = sum(1 for m in ms if m.get("signal"))
            surface = next((m["surface"] for m in ms if m.get("surface")), None)
            chips = f'<span class="chip">{esc(cat)}</span>'
            if surface:
                chips += f'<span class="chip">{_SURFACE_DE.get(surface.lower(), esc(surface))}</span>'
            if n_sig:
                chips += f'<span class="chip sig">{n_sig} Signal</span>'
            is_open = n_sig or (cat in _OPEN_CATS and n_open)
            rich = [m for m in ms if _is_rich(m)]
            flat = sorted((m for m in ms if not _is_rich(m)),
                          key=lambda m: (_STATUS_ORDER[m["status"]], m.get("time") or ""))
            out.append(
                f'<details class="am-tn"{" open" if is_open else ""}><summary>'
                f'<span class="tour">{esc(tn)}</span>{chips}'
                f'<span class="n">{len(ms)} {"Partie" if len(ms) == 1 else "Partien"}'
                f'{f" &middot; {n_open} offen" if n_open != len(ms) else ""}'
                f'</span></summary>'
                + (_RICH_HEAD + "".join(_am_match(m, thresh) for m in rich) if rich else "")
                + (_FLAT_HEAD + "".join(_am_line(m) for m in flat) if flat else "")
                + '</details>')
    return "".join(out)


def render(data: dict) -> str:
    thresh = pct(data["threshold"], 0)

    strip = [
        ("Modellbewertung", str(sum(1 for m in data["matches"]
                                    if m.get("method", "model") == "model")),
         f'von {data["n_scored"]} Partien insgesamt'),
        ("Signale", str(data["n_signals"]), f'EV über {thresh}'),
        ("Nur TA-Elo", str(sum(1 for m in data["matches"] if m.get("method") == "ta_elo")),
         "ohne Modellabdeckung"),
        ("Übersprungen", str(len(data["skipped"])), "gar keine Bewertung"),
        ("Referenzbücher", str(len(data["ref_books"])),
         ", ".join(list(data["ref_books"])[:3]) + ("…" if len(data["ref_books"]) > 3 else "")),
        ("Soft-Value", str(len(data.get("soft_value") or [])), "Seiten über Sharp-Fair"),
        ("Prediction Markets", str((data.get("prediction_markets") or {}).get("n_matched", 0)),
         "Partien mit Polymarket/Kalshi"),
        ("Arbitrage", str(len(data.get("arbs") or [])), "sichere Paare"),
    ]
    board = data.get("all_matches") or {}
    if board.get("days"):
        strip.insert(0, ("Alle Partien", str(sum(d["n"] for d in board["days"])),
                         f'heute &amp; morgen, {sum(d["n_upcoming"] for d in board["days"])} offen'))
        strip.insert(2, ("BetInAsia-Signale", str(board.get("n_signals", 0)),
                         f"EV ab {thresh} bei Pinnacle"))
    strip_html = "".join(
        f'<div class="stat"><div class="k">{k}</div><div class="v">{v}</div>'
        f'<div class="n">{n}</div></div>' for k, v, n in strip)

    n_sig = data["n_signals"]
    if n_sig:
        verdict = (f'<div class="verdict hit"><div class="icon">&#9679;</div><div>'
                   f'<h2>{n_sig} Partie(n) über der Schwelle</h2>'
                   f'<p>Das Modell weicht bei diesen Partien um mehr als {thresh} vom fairen '
                   f'Marktpreis ab. Vor einer Wette gegen den tatsächlich verfügbaren Preis '
                   f'prüfen &mdash; ein Edge gegen den Fairwert ist noch kein positiver '
                   f'Erwartungswert.'
                   + (f' Bei BetInAsia (Pinnacle-Preis) spielbar: {board.get("n_signals", 0)}.'
                      if board.get("days") else "")
                   + '</p></div></div>')
    else:
        verdict = ('<div class="verdict none"><div class="icon">&#9675;</div><div>'
                   '<h2>Kein Signal auf dieser Karte</h2>'
                   f'<p>Keine Partie erreicht {thresh} EV bei einem scharfen Buch. Das ist der '
                   'Normalfall und '
                   'gleichzeitig das ehrlichste Ergebnis: Das Modell reproduziert den '
                   'Sharp-Markt weitgehend, statt ihn zu schlagen.</p></div></div>')

    def build_rows(subset, show_edge=True):
        out = []
        for m in subset:
            a, b = m["sides"]
            fav = a if a["model_prob"] >= b["model_prob"] else b
            chip = "chip sharp" if m["ref_book"] in ("Pinnacle", "Betfair") else "chip"
            out.append(
                f'<div class="row"><div class="mhead">'
                f'<span class="tour">{m["tournament"]}</span>'
                f'{day_chip(m.get("date"))}'
                f'<span class="{chip}">{m["ref_book"]}</span>'
                f'<span class="chip">{m["tour"].upper()}</span>'
                f'{round_chip(m)}'
                f'{stale_chip(m.get("stale_players"))}'
                f'{fair_chip(m)}'
                f'<span>Marge {pct(m["ref_margin"], 1)}</span></div>'
                f'{forecast_line(m)}')
            for idx, sd in enumerate((a, b)):
                cls = "side fav" if sd is fav else "side"
                lo = min(sd["model_prob"], sd["market_prob"]) * 100
                hi = max(sd["model_prob"], sd["market_prob"]) * 100
                meta = (f'Elo {sd["elo"]:.0f} &middot; {sd["matches"]} Matches'
                        if sd["matches"] is not None else f'TA-Elo {sd["elo"]:.0f}')
                if show_edge:
                    ev = sd["ev_at_ref"]
                    ecls = "p" if ev > 0.005 else ("n" if ev < -0.005 else "z")
                    last = (f'<div class="cell"><span class="lbl">EV bei Quote</span>'
                            f'<span class="edge {ecls}">{pct(ev, 1, sign=True)}</span></div>')
                    meta += (f' &middot; Edge {pct(sd["edge"], 1, sign=True)}')
                else:
                    last = ('<div class="cell"><span class="lbl">EV bei Quote</span>'
                            '<span class="edge z" title="Kein EV-Wert: reine Elo-Prognose '
                            'ohne Marktinformation">&ndash;</span></div>')
                out.append(
                    f'<div class="{cls}">'
                    f'<div><div class="pname">{sd["player"]}</div>'
                    f'<div class="pmeta">{meta}</div>'
                    f'{side_stats(m, idx)}'
                    f'<div class="bar" role="img" aria-label="Prognose {pct(sd["model_prob"])} '
                    f'gegen Markt {pct(sd["market_prob"])}">'
                    f'<div class="gap" style="left:{lo:.1f}%;width:{hi - lo:.1f}%"></div>'
                    f'<div class="mk" style="left:{sd["market_prob"] * 100:.1f}%"></div>'
                    f'<div class="md" style="left:{sd["model_prob"] * 100:.1f}%"></div>'
                    f'</div></div>'
                    f'<div class="cell"><span class="lbl">Prognose</span>{pct(sd["model_prob"])}</div>'
                    f'<div class="cell"><span class="lbl">Markt</span>{pct(sd["market_prob"])}</div>'
                    f'<div class="cell"><span class="lbl">Fair / Quote</span>'
                    f'{sd["model_fair_odds"]:.2f} <span style="color:var(--faint)">/ '
                    f'{sd["ref_odds"]:.2f}</span></div>'
                    f'{last}</div>')
            out.append("</div>")
        return out

    model_matches = [m for m in data["matches"] if m.get("method", "model") == "model"]
    ta_matches = [m for m in data["matches"] if m.get("method") == "ta_elo"]
    rows = build_rows(model_matches)

    if data["skipped"]:
        items = "".join(f'<li>{s["match"]} &mdash; {s["reason"]}</li>' for s in data["skipped"])
        skipped = (f'<div class="sec"><h2>Nicht bewertet</h2><span class="rule"></span>'
                   f'<span class="count">{len(data["skipped"])}</span></div>'
                   f'<details class="skip"><summary>Warum diese Partien fehlen</summary>'
                   f'<p>Ein Spieler ohne ausreichende Historie startet bei Elo&nbsp;1500. '
                   f'Das erzeugt gegen den Markt einen großen Scheinvorteil &mdash; das '
                   f'attraktivste und wertloseste Signal, das dieses Modell produzieren kann. '
                   f'Solche Partien werden deshalb ausgeschlossen statt still mitgerechnet.</p>'
                   f'<ul>{items}</ul></details>')
    else:
        skipped = ""

    if ta_matches:
        ta_html = (
            '<div class="sec"><h2>Ohne Modellabdeckung</h2><span class="rule"></span>'
            f'<span class="count">{len(ta_matches)} Partien</span></div>'
            '<div class="verdict none" style="margin-bottom:12px">'
            '<div class="icon">&#9633;</div><div>'
            '<h2>Einschätzung von Tennis Abstract, kein Modellwert</h2>'
            '<p>Bei diesen Partien fehlt mindestens einem Spieler ausreichend Historie in '
            'unserer eigenen Datenbasis. Statt sie wegzulassen, steht hier Tennis Abstracts '
            'Elo-Prognose &mdash; deren Datenbasis umfasst auch Qualifikation, Challenger und '
            'ITF&nbsp;$50K+. Bewusst <b>ohne Edge-Wert</b>: eine reine Elo-Prognose kennt keinen '
            'Marktpreis und weicht auf dieser Karte im Mittel um 10,6&thinsp;% vom Markt ab '
            '(Modell: 1,5&thinsp;%). Gegen einen Markt, der auf 0,8&nbsp;Prozentpunkte genau '
            'kalibriert ist, heißt das fast immer: die Bewertung ist unvollständig, nicht der '
            'Preis falsch.</p></div></div>'
            '<div class="tbl"><div class="thead">'
            '<span>Spieler</span><span>TA-Prognose</span><span>Markt</span>'
            '<span>Faire Quote</span><span>EV bei Quote</span></div>'
            + "".join(build_rows(ta_matches, show_edge=False)) + '</div>')
    else:
        ta_html = ""

    aud = data["audit"]
    stamp = data["generated_at"].replace("T", " ").replace("+00:00", " UTC")
    out = HTML
    for k, v in {
        "__STAMP__": stamp, "__THRESH__": thresh, "__STRIP__": strip_html,
        "__VERDICT__": verdict, "__ROWS__": "".join(rows), "__SKIPPED__": skipped,
        "__TAROWS__": ta_html, "__NSCORED__": str(data["n_scored"]),
        "__FORECASTS__": forecast_section(data),
        "__ALLMATCHES__": all_matches_section(data),
        "__SOFTVALUE__": soft_value_section(data), "__PMBOARD__": pm_section(data),
        "__PMPROS__": pm_pros_section(data),
        "__ARBS__": arb_section(data), "__PRICEBOARD__": price_board_section(data),
        "__NMATCHES__": str(len(data["matches"])),
        "__NMODEL__": str(len(model_matches)),
        "__NTESTED__": f'{aud["matches_tested"]:,}'.replace(",", " "),
        "__ROI__": pct(aud["backtest_roi"], 2, sign=True),
        "__T__": f'{aud["backtest_t"]:.2f}',
        "__NBETS__": f'{aud["backtest_n"]:,}'.replace(",", " "),
        "__GAIN__": f'{aud["information_gain"]:+.5f}',
    }.items():
        out = out.replace(k, v)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--inp", type=Path, default=config.PROCESSED_DIR / "dashboard.json")
    ap.add_argument("-o", "--out", type=Path, default=config.REPORTS_DIR / "dashboard.html")
    args = ap.parse_args()
    data = json.loads(args.inp.read_text())
    args.out.write_text(render(data), encoding="utf-8")
    print(f"{args.out}  ({args.out.stat().st_size / 1024:.0f} KB, "
          f"{data['n_scored']} Partien, {data['n_signals']} Signale)")


if __name__ == "__main__":
    main()
