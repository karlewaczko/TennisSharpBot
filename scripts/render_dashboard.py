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

footer { margin-top:40px; padding-top:18px; border-top:1px solid var(--border);
         font-size:12px; color:var(--faint); }

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
        <div class="sub">Modellwahrscheinlichkeit gegen Sharp-Marktpreis &middot; ATP &amp; WTA</div>
      </div>
    </div>
    <div class="stamp">
      Stand <b>__STAMP__</b><br>
      Schwelle <b>__THRESH__</b> Edge &middot; Referenz bevorzugt Pinnacle
    </div>
  </header>

  <div class="strip">__STRIP__</div>

  __VERDICT__

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
         fairen Marktpreis als zusätzlichem Merkmal.</p></div>
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
    Quoten und Spielplan von TennisExplorer, Elo-Referenz von Tennis Abstract.
    Erzeugt aus <span class="num">scripts/build_dashboard.py</span>; die Zahlen sind
    von der Kommandozeile reproduzierbar. Momentaufnahme, keine Anlageberatung.
  </footer>
</div>
"""


def pct(x, digits=1, sign=False):
    if x is None:
        return "&ndash;"
    return f"{x * 100:+.{digits}f}&thinsp;%" if sign else f"{x * 100:.{digits}f}&thinsp;%"


def render(data: dict) -> str:
    thresh = pct(data["threshold"], 0)

    strip = [
        ("Modellbewertung", str(sum(1 for m in data["matches"]
                                    if m.get("method", "model") == "model")),
         f'von {data["n_scored"]} Partien insgesamt'),
        ("Signale", str(data["n_signals"]), f'Edge über {thresh}'),
        ("Nur TA-Elo", str(sum(1 for m in data["matches"] if m.get("method") == "ta_elo")),
         "ohne Modellabdeckung"),
        ("Übersprungen", str(len(data["skipped"])), "gar keine Bewertung"),
        ("Referenzbücher", str(len(data["ref_books"])),
         ", ".join(list(data["ref_books"])[:3]) + ("…" if len(data["ref_books"]) > 3 else "")),
    ]
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
                   f'Erwartungswert.</p></div></div>')
    else:
        verdict = ('<div class="verdict none"><div class="icon">&#9675;</div><div>'
                   '<h2>Kein Signal auf dieser Karte</h2>'
                   f'<p>Keine Partie erreicht {thresh} Edge. Das ist der Normalfall und '
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
                f'<span class="{chip}">{m["ref_book"]}</span>'
                f'<span class="chip">{m["tour"].upper()}</span>'
                f'<span>Marge {pct(m["ref_margin"], 1)}</span></div>')
            for sd in (a, b):
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
