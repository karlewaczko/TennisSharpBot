# Was fehlt, um den Markt zu schlagen — recherchiert und gemessen (2026-09-04)

Drei Hypothesen aus der Literatur, alle mit eigenen Daten geprüft.

## Ausgangslage

`audit_edge.py`, 55 124 Partien: Informationsgewinn **−0.00111**.
Unabhängige Replikation (nickdatak, 8 224 Partien): XGBoost Brier 0.2162
gegen Betfair 0.1988.

## Hypothese 1 — Aufschlag/Return-Features (Klaassen & Magnus)

Jedes punktbasierte Tennismodell beruht auf der Punktgewinnquote am
eigenen Aufschlag. Unser Feature-Satz hatte sie nie, weil
tennis-data.co.uk **keinerlei** Matchstatistik führt. Literatur meldet
3.8 % ROI über 2 173 Partien (2011).

Umgesetzt: `tennismylife.py` + `build_serve_features.py`. Exponentiell
gewichtete, leckfreie Aufschlag- und Returnraten über **195 444 Partien**
(Haupttour, Challenger, Quali, WTA), verknüpft mit unseren Quoten zu
62 357 Partien (79.6 % Trefferquote, davon 97.5 % mit Statistik).

| | Informationsgewinn |
|---|---|
| bisheriger Feature-Satz (Elo, Form, H2H, …) | −0.00111 |
| **nur Aufschlag/Return** | **−0.00026** |

Vier Mal näher an null, 7 von 13 Saisons positiv — aber netto weiterhin
**kein** Gewinn. Die Features sind weniger redundant zum Markt als unsere
bisherigen, reichen aber nicht.

## Hypothese 2 — Intransitivität (arXiv 2510.20454)

A schlägt B, B schlägt C, C schlägt A. Ein Skalar-Rating wie Elo kann das
strukturell nicht abbilden. Die Studie meldet 3.26 % ROI über 1 903
Wetten (p = 0.005) in Partien mit hoher Intransitivität.

Umgesetzt: gerichteter Siegesgraph über die volle Historie, 2-Jahres-
Fenster, Zykelstärke = min(Pfade A→C→B, Pfade B→C→A).

**Der Markt ist auf jeder Intransitivitätsstufe sauber kalibriert:**

| Zykelstärke | n | Marktprognose | tatsächlich | Fehler |
|---|---|---|---|---|
| 0 | 14 783 | 50.27 % | 50.19 % | −0.08pp |
| 1 | 8 689 | 49.33 % | 50.24 % | +0.90pp |
| 2–3 | 14 751 | 49.84 % | 49.98 % | +0.14pp |
| 4–6 | 15 666 | 49.72 % | 49.76 % | +0.04pp |
| 7+ | 8 468 | 49.90 % | 49.81 % | −0.09pp |

Der Log-Loss steigt mit der Zykelstärke (0.537 → 0.639), weil diese
Partien *schwerer* sind — nicht, weil der Markt sie falsch bepreist.

Und unser Beitrag wird dort **schlechter**, nicht besser:

| Teilmenge | n | Informationsgewinn |
|---|---|---|
| alle | 50 226 | −0.00023 |
| Zykelstärke ≥ 3 | 26 694 | **−0.00319** |
| Zykelstärke ≥ 5 | 15 450 | **−0.00638** |

Das Gegenteil der publizierten Behauptung. Einschränkung: unser Maß
(Zykel über gemeinsame Gegner) ist nicht identisch mit ihrem
spektralen Graphmaß, und ihre Stichprobe war auf Top-Turniere begrenzt.

## Hypothese 3 — Quotenvergleich zwischen Büchern

Bereits im bestehenden Audit gemessen: bet365 spielen, wann immer es
Pinnacles faire Quote schlägt — ROI +1.93 % (t = 1.27) bei EV > 0,
+9.26 % (t = 1.39) bei EV > 5 %. Alle Schwellen **nicht von null
unterscheidbar**.

## Was tatsächlich fehlt

Keine dieser Quellen enthält Information, die der Markt nicht schon hat.
Was fehlen würde, ist nicht *mehr* Statistik, sondern eine andere
Kategorie:

1. **Schneller als der Markt** — Verletzungsmeldungen, Aufgabe im
   Aufwärmen, Wetter, Platzgeschwindigkeit am Turniertag. Keine freie
   Quelle liefert das mit dem nötigen Vorlauf.
2. **Feiner als der Markt** — Punkt-für-Punkt-Daten (Sackmann Match
   Charting Project). In TennisMyLife nicht enthalten und nur für einen
   Bruchteil der Partien überhaupt erfasst.
3. **Größe statt Vorsprung** — Liquidität in Märkten, die scharfe Bücher
   gar nicht stellen. Das ist kein Modellproblem.

## Was die Arbeit trotzdem gebracht hat

Die neue Quelle ist der Sache nach besser, auch ohne Marktvorsprung:
195 444 statt 82 817 Partien, 6 031 statt 2 288 Spieler,
Aufschlagstatistik auf 94.8 % — und sie schließt die Lücke, die
`is_stale` überhaupt erst nötig machte.

## Nachtrag — Pressure Points / Clutch (tennisratio.com, 2026-09-04)

Pressure Points sind dort definiert als Punkte bei 0:30, 15:30, 30:40,
Einstand und Vorteil. Die Behauptung: Sie zeigen mentale Stärke über die
normalen Statistiken hinaus.

Geprüft am nächstliegenden Maß, das wir haben — Breakballrettung über
195 444 Partien, 354 755 Spieler-Matches. „Clutch" ist dabei die
Rettungsquote **abzüglich** der Quote, die die normale Aufschlagstärke
schon erwarten lässt: genau der Überschuss, den solche Statistiken zu
isolieren behaupten.

### Beständigkeit (erste gegen zweite Karrierehälfte, 1 255 Spieler)

| Merkmal | r |
|---|---|
| Aufschlagquote (bekannte Fähigkeit) | **+0.884** |
| Breakballrettung roh | +0.694 |
| **Clutch-Überschuss** | **+0.064** |

Die rohe Breakballquote ist beständig — aber nur, weil gute Aufschläger
mehr Breakbälle retten. Es ist Aufschlagstärke unter anderem Namen. Der
Überschuss darüber hinaus sagt über die Zukunft praktisch nichts.

### Der Einwand „mehr Punkte, weniger Rauschen" trägt nicht

Pressure Points erfassen mehr Punkte je Spiel als Breakbälle, also
weniger Messrauschen. Wäre das die Ursache, müsste die Beständigkeit mit
der Stichprobe steigen. Sie tut es nicht:

| Breakbälle je Hälfte | Spieler | r |
|---|---|---|
| 150–300 | 169 | +0.058 |
| 300–600 | 362 | +0.079 |
| 600+ | 724 | +0.060 |

Flach über einen vierfachen Stichprobenbereich.

### Varianzzerlegung

Bei Spielern mit mindestens 300 Breakbällen (n = 1 486): beobachtete
Streuung zwischen Spielern 0.0178, allein durch Zufall zu erwarten
0.0165. Echte Fähigkeitsstreuung: **0.0065**, also 0.65 Prozentpunkte
über die gesamte Tour.

Clutch existiert also, ist aber so klein, dass der Markt praktisch alles
davon übersehen müsste, damit daraus ein Vorsprung würde.

## Pressure Points mit den echten Daten (tennisratio.com, 2026-09-04)

Der Nachtrag oben stützte sich auf Breakbälle als Näherung, mit dem
offenen Einwand, die Stichprobe je Match sei zu dünn. Dieser Abschnitt
prüft dieselbe Frage mit den tatsächlichen Druckpunkten.

### Die Quelle

tennisratio.com veröffentlicht je Match die Punkte nach Spielstand —
0:30, 0:40, 15:30, 15:40, 30:30, 30:40, 40:40, 40:A — getrennt für
Aufschlag und Return, jeweils mit Zähler *und* Nenner, dazu die Quoten
beider Spieler. Keine andere unserer Quellen führt Spielstände.

robots.txt sperrt `/api/`; die Spielerseiten sind erlaubt und tragen die
Matchdaten im eigenen HTML. Der Loader liest nur diese, mit 1,5 s Pause
und lokalem Zwischenspeicher.

Erfasst: **350 Spieler, 79 878 Spieler-Matches, 1 681 732 Druckpunkte am
Aufschlag**, zurück bis 2001.

### Der Effekt ist null

| | |
|---|---|
| Druckpunktquote am Aufschlag | 0.6131 |
| Basisquote im selben Match | 0.6125 |
| **Überschuss** | **+0.0006** |

Spieler gewinnen Druckpunkte praktisch genau mit ihrer normalen Quote.

### Beständigkeit — besser als über Breakbälle, aber schwach

| Merkmal | r (Breakball-Näherung) | r (echte Druckpunkte) |
|---|---|---|
| Basisquote am Aufschlag | +0.884 | **+0.925** |
| Druckquote roh | +0.694 | +0.866 |
| **Clutch-Überschuss** | +0.064 | **+0.142** |

Der Einwand war also berechtigt: Mit der dichteren Messung steigt die
Beständigkeit deutlich. Sie bleibt trotzdem schwach — und die rohe
Druckquote ist mit +0.857 weiterhin fast vollständig Aufschlagstärke
unter anderem Namen.

### Gegen die Quoten

Leckfreie, exponentiell gewichtete Clutch-Bewertung je Spieler, gepaart
über beide Seiten, gegen die mitgelieferten Quoten:

20 450 gepaarte Partien, 17 120 getestet:

| Saison | n | Markt | kombiniert |
|---|---|---|---|
| 2023 | 3 066 | 0.6187 | 0.6324 |
| 2024 | 3 864 | 0.6166 | 0.6233 |
| 2025 | 5 324 | 0.6236 | 0.6249 |
| 2026 | 4 866 | 0.6101 | 0.6127 |

**Informationsgewinn −0.0051**, in allen vier Saisons negativ. Der
Vollabzug halbiert den Wert gegenüber der ersten Teilstichprobe
(−0.01089 auf 4 424 Partien), was die dortige Überanpassung bestätigt —
er dreht das Vorzeichen aber nicht.

### Gesamtbild

| Ansatz | Informationsgewinn |
|---|---|
| bisheriger Feature-Satz | −0.00111 |
| Aufschlag/Return | −0.00026 |
| Belaggeschwindigkeit | −0.00058 |
| Intransitivität (Zielsegment) | −0.00638 |
| **Druckpunkte / Clutch** | **−0.00510** |

## Nach Segment aufgeschlüsselt — wo ist der Markt schwach? (2026-09-04)

### War der Druckpunkt-Test beide Touren?

Ja. Der tennisratio-Abzug enthält 30 376 ATP-, 28 092 WTA- und 18 150
Grand-Slam-Partien. Der Aufschlag/Return-Test lässt sich zudem sauber
trennen:

| | n | Markt | kombiniert | Gewinn |
|---|---|---|---|---|
| beide Touren | 50 226 | 0.58666 | 0.58690 | −0.00023 |
| nur ATP | 25 180 | 0.57858 | 0.58077 | −0.00219 |
| nur WTA | 25 046 | 0.59479 | 0.59783 | −0.00303 |

**Die WTA ist nicht weicher.** Das widerlegt eine gängige Annahme: Der
WTA-Markt hat zwar einen höheren Log-Loss (0.595 gegen 0.579), aber das
heißt nur, dass WTA-Partien schwerer vorherzusagen sind — nicht, dass
der Preis falsch ist. Unser Beitrag ist dort sogar etwas schlechter.

### Ist irgendein Segment fehlbepreist?

Kalibrierungsfehler je Wahrscheinlichkeitsband, gemessen als z-Wert
gegen den eigenen Standardfehler. Rohe Prozentabweichungen täuschen:
kleine Segmente zeigen immer große Fehler.

| Segment | n | größtes \|z\| | mittleres \|z\| |
|---|---|---|---|
| ALLE | 78 351 | 2.31 | 1.03 |
| ATP | 40 514 | 2.54 | 1.15 |
| WTA | 37 837 | 1.59 | 0.79 |
| Grand Slam | 15 934 | 1.92 | 0.88 |
| Masters 1000 | 8 947 | 2.51 | 1.48 |
| ATP500 | 6 332 | 2.99 | 1.14 |
| WTA250 | 4 081 | 1.26 | 0.52 |
| 2. Runde | 21 907 | 3.17 | 1.42 |
| Halbfinale | 3 747 | 2.85 | 1.40 |
| Finale | 1 875 | 0.74 | 0.45 |

Über rund 90 geprüfte Bänder liegt das mittlere \|z\| überall bei etwa 1
— genau der Wert, den ein perfekt kalibrierter Markt erzeugt. Die
Handvoll Werte über 2 ist bei so vielen Tests zu erwarten. **Kein
Segment ist belastbar fehlbepreist**, auch nicht die kleinen Turniere,
die Außenseiter oder die späten Runden.

### Was der Markt also noch nicht weiß

Nach allem Gemessenen: nichts, was sich aus vergangenen Ergebnissen
ableiten lässt. Übrig bleibt nur Information, die **nach** der
Preisstellung entsteht — Verletzung, Krankheit, Aufgabe im Aufwärmen,
Wetterumschwung. Das ist kein Modellproblem, sondern ein
Geschwindigkeitsproblem.

Ungeprüft geblieben, weil uns die historischen Daten dafür fehlen:
Eröffnungs- gegen Schlussquote. Wir ziehen Eröffnungsquoten live von
TennisExplorer, haben aber kein Archiv, um sie rückwirkend zu testen.
Das wäre der einzige Ansatz, den ich noch für aussichtsreich halte —
nicht weil das Modell besser wäre, sondern weil die frühe Quote weicher
ist als die späte.
