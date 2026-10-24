# Wie Profis wetten, wo ihr Geld hingeht — und wo unser Edge liegen kann

Stand: 22./23. Oktober 2026. Alles Gemessene ist mit Skript und Datei genannt
und reproduzierbar; alles Recherchierte ist mit Quelle verlinkt.

## Kurzfazit

1. **Profis schlagen den Markt nicht mit besseren Formeln, sondern mit
   besseren Preisen.** Die stärksten Tennis-Modelle der Welt (Syndikate wie
   Jasis) verkaufen ihre Preise inzwischen an Pinnacle — sie *sind* der
   Pinnacle-Preis. Unser Audit misst dasselbe von der anderen Seite: über
   55 124 Partien bringt kein Merkmal, das wir kennen, Information über den
   Pinnacle-Schlusskurs hinaus (Informationsgewinn −0,00111). Das gilt auch
   nach allen Nachtests (Aufschlag/Return, Belagstempo, Intransitivität,
   Druckpunkte, Segmente).
2. **Die Kennzahl ist der Schlusskurs, nicht die Trefferquote.** Wer
   regelmäßig Quoten bekommt, die über Pinnacles entvigtem Schlusskurs
   liegen (positiver Closing Line Value), gewinnt langfristig — und wird von
   weichen Büchern genau deshalb limitiert.
3. **Wo das Geld hingeht:** asiatische Bücher über Broker (Pinnacle, SBOBET,
   ISN, Singbet — genau das, was BetInAsia anbietet), Börsen (Betfair,
   Matchbook), weiche Bücher nur bis zur Limitierung, und seit 2025/26
   Prediction Markets (Kalshi in den USA, Polymarket mit offiziellem
   ATP-Vertrag). **Aus Deutschland** sind Kalshi (nur US-Kunden) und
   Polymarket (Geoblock, GGL-Sperrliste seit September 2025) keine Wettplätze
   — nur Preisquellen.
4. **Gebaut:** ein Preisbrett im Dashboard (jedes Buch gegen den Fairwert,
   Polymarket und Kalshi gegen den Sharp-Markt, Arbitrage über alle Plätze,
   ITF eingeschlossen), vier Läufe pro Tag per GitHub Actions, ein
   Quoten-Logbuch für Eröffnungs- gegen Schlusskurs und ein CLV-Report.
5. **Gemessen:** Polymarket und Kalshi liegen im Median 0,3 Prozentpunkte
   neben Pinnacle und sind nach Gebühr nie im Plus; weiche Bücher liegen zum
   Spielbeginn in 0 von 1 048 Seiten über Pinnacles Fairwert; Pinnacles
   Eröffnungskurs hat *negativen* CLV (die Eröffnungsmarge ist 4,6 %). Was
   bleibt, sind die Stunden dazwischen: acht Soft-Seiten im Plus auf der
   Karte vom 23. Oktober, eine Arbitrage von 1 % mit Polymarket-Bein. Zahlen
   in Abschnitt 4.

## 1. Wie Profis wetten

### 1.1 Syndikate und Modelle

- **Die Modelle sitzen im Preis.** Das britische Tennis-Syndikat Jasis Group
  ist Teil von Pinnacles B2B-Quotendienst 10Star; der Branchenbericht nennt
  schrumpfende Limits weltweit als Grund, warum Syndikate vom Wetten ins
  Preisverkaufen wechseln ([Legal Sports Report](https://www.legalsportsreport.com/67318/starlizard-us-sports-betting-industry-syndicates/)).
  Wer gegen Pinnacle wettet, wettet gegen diese Modelle.
- **Pinnacles Geschäftsmodell** ist, die Linie von scharfen Wettern formen zu
  lassen: kleine Limits bei Eröffnung, dann hohe Limits, Gewinner werden nicht
  gesperrt ([Wikipedia: Pinnacle Sports](https://en.wikipedia.org/wiki/Pinnacle_Sports)).
  Deshalb ist Pinnacles entvigter Kurs der beste öffentlich verfügbare
  Schätzer der wahren Wahrscheinlichkeit — unser Audit findet ihn über 157 000
  Spielerseiten auf 0,76 Prozentpunkte kalibriert.
- **In-Play und Latenz.** Der zweite große Profi-Edge ist Geschwindigkeit:
  Courtsiding (Punkte vom Platz schneller melden als der Schiedsrichter-Feed),
  Modelle, die nach jedem Punkt neu bewerten, und Wetten in die Sekunden,
  bevor die Bücher nachziehen ([Wikipedia: Courtsiding](https://en.wikipedia.org/wiki/Courtsiding),
  [FiveThirtyEight](https://fivethirtyeight.com/features/inside-the-shadowy-world-of-high-speed-tennis-betting),
  [Huck](https://www.huckmag.com/article/inside-the-murky-world-of-tennis-courtsiding)).
  Das ist Infrastruktur, kein Modell, an Turnieren verboten und nichts, was
  ein Hobbyprojekt nachbaut.

### 1.2 Die Kennzahl: Closing Line Value

Buchmacher erkennen Gewinner nicht an Gewinnen, sondern daran, ob die Linie
nach ihrer Wette in ihre Richtung läuft ([Action Network](https://www.actionnetwork.com/education/sports-betting-market-terms-and-strategies),
[How Gambling Works](https://howgamblingworks.substack.com/p/the-truth-about-limits)).
Der Grund ist Statistik: Bei 5 % Vorteil braucht man tausende Wetten, bis das
Ergebnis die Varianz übertönt; der Schlusskurs urteilt dagegen Partie für
Partie. Deshalb protokolliert das Dashboard jetzt jeden Lauf
(`data/processed/odds_snapshots.csv`, `data/processed/picks_log.csv`) und
`scripts/report_clv.py` rechnet jede markierte Seite gegen den letzten Kurs
vor Spielbeginn ab.

### 1.3 Wo das Geld hingeht

| Platz | Marge | Limits / Sperren | Aus Deutschland |
|---|---|---|---|
| Pinnacle, SBOBET, ISN, Singbet über Broker (BetInAsia, Sportmarket) | 2–3 % | hoch, keine Gewinner-Sperren | über Broker erreichbar; Anbieter ohne deutsche Lizenz — rechtliche Grauzone, Wettsteuer selbst zu klären |
| Weiche Bücher (bet365, bwin, Tipico, Betano, Interwetten …) | 5–10 % | Limit nach Wochen bei positivem CLV | GGL-lizenziert, LUGAS-Limit 1 000 €/Monat, **5,3 % Wettsteuer** meist an den Kunden weitergegeben |
| Börsen (Betfair Exchange, Matchbook) | 2–5 % Kommission auf Gewinne | keine Sperren | Betfair Exchange hat den deutschen Markt verlassen |
| Kalshi | Taker 0,07·p·(1−p) je Kontrakt | keine Sperren | **nur US-Kunden** |
| Polymarket | Taker 0,05·p·(1−p) je Anteil (Sport), Maker 0 | keine Sperren | **Geoblock, GGL-Sperrliste** ([GGL-Warnung, Sept. 2025](https://publicgaming.com/news-categories/regulatory-issues/14898-the-ggl-has-stressed-that-platforms-such-as-polymarket-are-not-licensed-in-the-country)) |

Was das für BetInAsia heißt: Dort ist der Preis schon scharf. Der klassische
„Top-down"-Edge (weiches Buch zahlt mehr als Pinnacles Fairwert) existiert
dort per Definition nicht; was bleibt, sind **Linienbewegung** (früh die
Seite nehmen, in die der Markt läuft) und **Marktvergleich** zwischen den
Büchern des Brokers. Beides misst das neue Logbuch.

Die **5,3 % Wettsteuer** ist in Deutschland der größte stille Gegner: Ein
Buch, das sie an den Kunden weiterreicht, verwandelt einen Preis mit +4 % EV
in einen mit −1 %. Jede Value-Rechnung auf einem GGL-Buch muss die Steuer
abziehen, bevor sie zählt.

### 1.4 Welche Märkte

Der Match-Winner ist der schärfste Markt. Handicaps, Totals und Satzwetten
bekommen weniger Aufmerksamkeit (Polymarket listet pro Match 16 davon), und
Challenger/ITF-Linien sind weicher — aber die Limits dort sind winzig, und
auf ITF-Ebene ist Spielmanipulation ein reales Integritätsrisiko für beide
Seiten der Wette. Kalshi und Polymarket listen inzwischen beide ITF-Matches
bis M15/W15 ([Prediction News, Okt. 2026](https://predictionnews.com/story/rita-reviews-compares-kalshi-alternatives-for-tennis-event-contracts)),
Polymarket ist seit August 2026 offizieller Prediction-Market-Partner der ATP
mit 20 000 Matches pro Saison einschließlich Challenger ([Yahoo Sports](https://sports.yahoo.com/articles/polymarket-becomes-official-prediction-markets-222049150.html)).

## 2. Warum unser Modell den Markt nicht schlägt — und was stattdessen zählt

Alle Messungen stehen in `data/reports/market_edge_research.md` und
`data/processed/edge_audit_summary.json`:

| Hypothese | Ergebnis |
|---|---|
| Elo, Form, H2H, Ermüdung + Marktpreis | Informationsgewinn −0,00111 (55 124 Partien, 13 Saisons) |
| Aufschlag-/Return-Raten (TennisMyLife, 195 444 Partien) | −0,00026 |
| Belagstempo (Tennis Abstract) | −0,00041 |
| Intransitivität (arXiv 2510.20454) | −0,00319 / −0,00638 |
| Druckpunkte (tennisratio.com, 1,68 Mio. Punkte) | −0,0051; Effekt +0,0006 |
| Segmente (Tour, Level, Runde, Belag) | z-Werte im Mittel 1,0 — kein Segment fehlbepreist |
| Tennis-Abstract-Draw-Forecast vs. Markt | TA weicht 6,45 pp ab, unser Modell 1,24 pp |

Das „perfektionierte" Modell ist deshalb **marktverankert**: Der faire Preis
kommt vom scharfen Markt, das Modell ist eine Plausibilitätsprüfung
obendrauf, und der Edge wird dort gesucht, wo Profis ihn finden — im
Preisvergleich und in der Zeit.

## 3. Was eingebaut wurde

| Baustein | Datei | Was es tut |
|---|---|---|
| Polymarket-Anbindung | `src/tennissharp/data/polymarket.py` | Gamma-API (Tag 864), offene Einzel-Moneylines ATP/WTA/ITF, Bid/Ask, Liquidität, Startzeit, Gebührenformel |
| Kalshi-Anbindung | `src/tennissharp/data/kalshi.py` | Serien KXATPMATCH, KXWTAMATCH, KXATPCHALLENGERMATCH, KXWTACHALLENGERMATCH, KXITFMATCH, KXITFWMATCH; Orientierung über Event-Ticker; Turnier/Runde aus dem Regeltext; Gebühren je Serientyp |
| Preisvergleich | `src/tennissharp/market_compare.py` | Namensabgleich „Van Assche L." ↔ „Luca Van Assche", gebührenbereinigte Quoten, EV gegen Fairwert, Arbitrage, Fairwert-Anker aus liquiden Mittelkursen, Snapshots, CLV |
| Dashboard | `scripts/build_dashboard.py`, `scripts/render_dashboard.py` | Sektionen „Sharp gegen Soft", „Polymarket & Kalshi", „Arbitrage", „Alle Preise"; ITF über `--itf-limit`; Startzeit-Sperre gegen In-Play |
| Logbuch + CLV | `data/processed/odds_snapshots.csv`, `picks_log.csv`, `scripts/report_clv.py` | Eröffnungs- und Schlusskurs je Buch und Partie; jede markierte Seite gegen den Schlusskurs; Abrechnung mit Ergebnissen |
| Linienstudie | `scripts/study_line_movement.py` | Eröffnung gegen Schluss auf den Ergebnissen der letzten Tage (TennisExplorer führt je Buch die komplette Quotenhistorie) |
| Automatik | `.github/workflows/dashboard.yml`, `update-data.yml`, Claude-Code-Zeitplan | Preisbrett 03:17, 09:17, 15:17, 21:17 UTC; Tennis-Abstract-Elo dienstags 05:53 UTC über Claude Code, weil Tennis Abstract GitHub sperrt; Spielertabelle und Modell dienstags 06:41 UTC |

Technische Fakten, die beim Bauen geprüft wurden:

- Polymarket: `bestBid`/`bestAsk` gelten für das Token des ersten Ergebnisses;
  die Gegenseite ist das Komplement. Gebühren laut
  [docs.polymarket.com](https://docs.polymarket.com/trading/fees): nur Taker,
  `Anteile × 0,05 × p × (1−p)` im Sport, Maker gebührenfrei. 100 Anteile zu
  0,50 $ kosten 1,25 $ Gebühr — 2,5 % des Einsatzes.
- Kalshi: Preise als Dollar-Strings (`yes_bid_dollars`), zwei Märkte je
  Match; Serien `fee_type` „quadratic" (Taker 0,07·p·(1−p), Maker frei) bzw.
  „quadratic_with_maker_fees" (ATP/WTA-Hauptserien, Maker 0,0175). Die
  öffentliche API drosselt Bursts (429) — die Anbindung wartet und wiederholt.
- TennisExplorer zeigt für ITF-Matches meist keine Buchmacher-Tabelle, nur die
  anonyme Spielplan-Quote; die geht nie in die Arbitrage ein.

## 4. Gemessen auf der ersten Karte (23. Oktober 2026, Lauf 22:02 UTC)

Alle Zahlen aus `data/processed/dashboard.json`; die Seite dazu ist
`docs/index.html`.

**Umfang.** 71 Partien auf dem Preisbrett (20 Tour, 11 Challenger, 40 ITF),
davon 31 mit Modell- oder Elo-Bewertung (20 Modell, 11 Tennis-Abstract-Elo),
0 Signale, 8 übersprungen, 146 des Tages schon gespielt. Fairwert-Quelle: 9
Partien mit scharfem Buch (Pinnacle 3, Betfair 6 — TennisExplorer führt
Pinnacle am Vorabend nur selten), 26 mit liquidem Prediction-Market-Mittelkurs,
36 nur mit weicher oder anonymer Quote.

**Prediction Markets.** Polymarket 148 offene Moneylines, Kalshi 148;
86 Partien der Karte wurden per Namensabgleich zugeordnet, 132 Seiten
verglichen. Gegen den Fairwert eines scharfen Buches (32 Seiten) liegt der
Mittelkurs im Mittel 0,93 Prozentpunkte daneben, im Median 0,31. Nach
Taker-Gebühr ist **keine** Seite im Plus. Übersetzt: Die Prediction Markets
*sind* der Sharp-Markt, mit Gebühr obendrauf. Als Preisquelle sind sie damit
gut genug, um dort als Fairwert zu dienen, wo kein scharfes Buch quotiert —
als Wettplatz (selbst wenn er erreichbar wäre) bieten sie gegen Pinnacle
nichts.

**Sharp gegen Soft.** 284 Seiten weicher Bücher gegen den Fairwert: im Mittel
−7,4 % (das ist die Marge), 2,8 % der Seiten im Plus. Die acht positiven:

| Partie | Seite | Buch | Quote | Fair (Quelle) | EV |
|---|---|---|---|---|---|
| Cherbourg ITF, Bolkvadze – Jorge | Bolkvadze | William Hill | 2,05 | 1,89 (Betfair) | +8,4 % |
| Lyon, Altmaier – Fritz | Altmaier | bet365 | 4,33 | 4,08 (Polymarket-Mid) | +6,1 % |
| dito | Altmaier | Betway | 4,25 | 4,08 | +4,1 % |
| dito | Altmaier | Betsson, Interwetten, bet-at-home | 4,20 | 4,08 | +2,9 % |
| dito | Altmaier | 1xBet | 4,18 | 4,08 | +2,4 % |
| dito | Altmaier | bwin | 4,10 | 4,08 | +0,4 % |

Das ist das Muster, von dem Profis leben: Ein Preis bewegt sich (Altmaier
wurde bei Polymarket von 0,225 auf 0,245 gekauft), und die weichen Bücher
stehen noch auf der alten Linie. Ob die Bewegung recht hatte, sagt erst der
Schlusskurs — deshalb steht die Seite jetzt im Logbuch (`picks_log.csv`) und
wird von `report_clv.py` abgerechnet. Ein GGL-Buch mit 5,3 % Steuer macht aus
+6,1 % ungefähr +0,5 %.

Wie schnell so etwas verschwindet, zeigte der nächste Lauf sieben Minuten
später (22:09 UTC, der Stand der veröffentlichten Seite): bet365 hatte
Altmaier von 4,33 zurückgenommen, Betway, Interwetten und 1xBet ebenso; übrig
blieb Betsson mit 4,10 (+0,4 %). Von acht positiven Seiten waren noch drei da.
Wer diesen Edge spielen will, braucht die Quote in der Minute, in der sie
steht — ein weiterer Grund, warum ein Lauf am Morgen nichts davon sieht.

**Arbitrage.** Genau eine: Bolkvadze bei William Hill 2,05 und Jorge bei
Polymarket 1,99 netto, Summe 0,990, also +1,0 % sicher — mit einem
Polymarket-Bein, aus Deutschland nicht spielbar. Knappstes Paar ohne
Prediction Market: Medvedev 1xBet 1,18 / Atmane Betfair 5,75, Summe 1,021.
Das Altmaier/Fritz-Paar bet365 4,33 / Polymarket 1,30 summiert auf 1,0002 —
null Marge, aber keine Arbitrage.

**Modell.** Bestes EV Altmaier zu 4,00 bei William Hill (+3,5 %), unter der
Schwelle, und mit dem Vermerk „Daten veraltet" für Fritz: Der Elo-Zustand
stammt vom 5. September, weil tennis-data.co.uk aus dieser Umgebung seit dem
Neustart 403 liefert. Die Modellzeilen sind deshalb an diesem Abend nur
Plausibilität, keine Signale; das Preisbrett ist davon unabhängig. Die
Wayback Machine hält die Saisondatei nur mit Stand 3. August, also älter als
der Zustand selbst. Erneuert wird das Modell vom wöchentlichen
GitHub-Actions-Lauf am Dienstag, der aus einem anderen Netz lädt, oder von
einem lokalen `python scripts/update_data.py` auf einem Rechner, den
tennis-data.co.uk nicht blockt. GitHub plant Workflows nur vom Standardzweig
`main`; dort liegen sie seit dem 24. Oktober. Tennis-Abstract-Elo und
Belagstempo wurden am 22. Oktober direkt nachgeladen, deshalb sind die
Elo-Fallback-Zeilen aktuell.

**Linienstudie: Eröffnung gegen Schluss** (`scripts/study_line_movement.py`,
Ergebnisse vom 19. und 20. Oktober, 52 Partien mit vollständiger
Pinnacle-Historie, 35 Challenger und 17 Tour; `data/reports/line_movement.json`):

| Messgröße | Wert |
|---|---|
| Bewegung Pinnacle Eröffnung → Schluss (Wahrscheinlichkeit) | 1,7 pp im Mittel |
| Favorit verkürzt / driftet | 48 % / 52 % — keine Richtung |
| Marge der Eröffnungslinie | 4,6 % (Median 4,9 %), am Schluss 2–3 % |
| CLV, wer den Eröffnungskurs nimmt: Favorit / Außenseiter | **−3,3 % / −7,8 %** |
| Realisiert zum Eröffnungskurs: Favorit / Außenseiter | −9,1 % / +2,9 % (Rauschen bei 52) |
| Weiche Bücher zum Schluss über Pinnacles Fairwert | **0 von 1 048 Seiten** (13 Bücher) |

Zwei Dinge folgen daraus. Erstens ist „früh wetten" bei Pinnacle selbst kein
Edge: Die Eröffnungslinie trägt fast doppelt so viel Marge wie der Schluss,
und sie sitzt auf dem Außenseiter — wer den Eröffnungskurs nimmt, bezahlt
sie. Zweitens ist zum Spielbeginn bei den weichen Büchern nichts mehr übrig.
Value gegen den Sharp-Markt entsteht, wenn überhaupt, **zwischen** Eröffnung
und Schluss, in den Stunden, in denen ein Buch nach einer Bewegung noch nicht
nachgezogen hat (der Altmaier-Fall oben), und ist bis zum Schluss weg. Genau
deshalb läuft das Preisbrett viermal am Tag; ein Morgenlauf würde es
verfehlen. Einschränkung: zwei Spieltage sind eine Stichprobe, keine
Statistik; die Studie läuft wöchentlich weiter.



## 4b. Tennis Abstract vollständig genutzt (23. Oktober 2026)

Was Tennis Abstract maschinell hergibt, und was davon jetzt in der Karte steckt:

| Tennis-Abstract-Quelle | Status | Verwendung |
|---|---|---|
| Elo-Tabellen ATP/WTA (`/reports/*_elo_ratings.html`): Elo, Hard/Clay/Grass-Elo, Peak, Alter, offizieller Rang | **neu für jede Partie**, nicht mehr nur als Ersatz | TA-Elo-Prognose (belagsspezifisch), Spielerzeile mit TA-Elo, Belag-Elo, Rang, Alter |
| Turnierprognosen (`/current/2026ATPLyon.html` usw., von der Startseite verlinkt) | **neu**: Seiten sind serverseitig gerendert, die Projektion steckt als `projCurrent` im Quelltext | TA-Forecast je Paarung der nächsten Runde (Summe der beiden Werte = 100 %), H2H, Titelchance; 37 Paarungen in 10 Turnieren am 23.10. |
| Belagstempo (`/reports/atp_surface_speed.html`, `surface-speed.cgi`) | im Einsatz, am 22.10. neu geladen | Belag je Turnier, Tempo-Merkmal |
| Spieler-Matchlogs (`/jsfrags/`), Leader-Quelldateien (`/jsmatches/`), Spielerlisten (`/jsplayers/`) | **nicht abgerufen** | robots.txt verbietet diese drei Pfade. Die bisherige Leaderboard-Abfrage las `/jsmatches/leadersource*.js` und ist abgeschaltet; die 50 Leader-Tabellen entstehen jetzt aus derselben Statistik bei TennisMyLife |
| Match-Statistiken (Asse, Doppelfehler, erste/zweite Aufschlagpunkte, Breakbälle) | **neu** über TennisMyLife, das Sackmanns Schema spiegelt (die Daten hinter den TA-Spielerseiten; 25 880 Partien seit Dezember 2024, 98,5 % mit Statistik) | Profil je Spieler über 52 Wochen, gesamt und auf dem Belag: Aufschlag- und Returnpunkte, Hold, Break, Ass-/Doppelfehlerquote, Form, H2H; daraus das Barnett-Clarke-Punktmodell |
| Sackmanns GitHub (`tennis_atp`, `tennis_wta`, Match Charting Project) | aus dieser Umgebung nicht erreichbar (404 über den Proxy) | TennisMyLife deckt dasselbe Schema ab; das Charting-Projekt bleibt offen |

**Prognosevergleich.** Jede bewertete Partie zeigt jetzt fünf Zahlen
nebeneinander: Markt, Modell, TA-Elo, TA-Forecast, Statistikmodell, jeweils mit
Abweichung vom Markt. Jeder Lauf schreibt sie in
`data/processed/forecasts_log.csv`; `scripts/report_clv.py --forecasts`
rechnet sie gegen die Ergebnisse ab (Brier, Log-Loss je Quelle). Erst dieser
Vergleich sagt, ob Tennis Abstracts Elo dem Markt irgendwo näher kommt als
unser Modell. Erste Messung auf der Karte vom 23. Oktober (Lauf 06:24 UTC),
Abstand zum fairen Marktpreis je Quelle:

| Quelle | Partien | Median | Mittel |
|---|---|---|---|
| Modell (mit Marktpreis) | 17 | 1,0 pp | 1,0 pp |
| TA-Elo (Belag) | 27 | 3,8 pp | 8,0 pp |
| TA-Forecast | 27 | 3,8 pp | 7,5 pp |
| Statistikmodell | 28 | 7,7 pp | 10,7 pp |

Das deckt sich mit der Septembermessung (TA 6,45 Punkte, Modell 1,24) bei
einem auf 0,8 Punkte kalibrierten Markt. Die größten TA-Abweichungen liegen
auf Challenger-Ebene (Misolic 85 % gegen 56 % Markt in Florenz, Pellegrino
84 % gegen 64 % in Lissabon), wo Elo von Challenger-Siegen lebt und der Markt
mehr weiß. Das Statistikmodell ist
absichtlich schlicht (ein Aufschlag- und ein Returnwert je Spieler) und weicht
entsprechend stark ab; es steht da, weil es die einzige Prognose ist, die weder
Elo noch Markt kennt.

**Nebenbefund.** Die Match-Seite von TennisExplorer nennt Hallenturniere
„indoors" ohne Belag; der Namensabgleich fiel dann auf die Frühjahrsausgabe
zurück und bewertete Lyon im Oktober auf Sand. Hallentennis ist Hartplatz;
das ist korrigiert.

## 5. Datenquellen — Bewertung

| Quelle | Taugt für | Status |
|---|---|---|
| tennis-data.co.uk | Historie + Schlussquoten mehrerer Bücher (Training, Backtest) | im Einsatz; Cloudflare lieferte aus dieser Umgebung 403, GitHub Actions läuft mit `continue-on-error` |
| TennisExplorer | Spielplan, Startzeiten, **Quotenhistorie je Buch mit Eröffnungskurs**, Ergebnisse | im Einsatz; jetzt auch Startzeit und Preisbrett |
| Tennis Abstract | Elo (auch ITF 50K+), Belagstempo, Turnierprognosen | im Einsatz; Elo nur live, nicht für Training; Matchlogs und Leader-Quellen per robots.txt gesperrt |
| TennisMyLife | Challenger/Quali/WTA-Ergebnisse mit Aufschlagstatistik | im Einsatz für den Aktivitätsindex; Serve-Features gemessen ohne Gewinn |
| tennisratio.com | Druckpunkte je Match | gemessen: kein Effekt |
| Sackmann `tennis_atp`/`tennis_wta` (GitHub) | Historie inkl. Futures/ITF, Punkt-für-Punkt der Slams | nicht eingebunden; ohne Quoten kein Beitrag zur Edge-Frage |
| gmalbert, nickdatak (GitHub) | unabhängige Replikationen | nickdatak: XGBoost-Brier 0,2162 gegen Betfair 0,1988 — bestätigt unseren Befund |
| The Odds API | Live-Quoten vieler Bücher | Client vorhanden, braucht eigenen Schlüssel |
| Polymarket Gamma API | Prediction-Market-Preise ATP/WTA/ITF | **neu im Einsatz** |
| Kalshi Trade API | Prediction-Market-Preise ATP/WTA/Challenger/ITF | **neu im Einsatz** |
| Pinnacle/PS3838-API über Broker | eigene Limits und Preise in Echtzeit | nicht eingebunden; nur mit Kontozugang |
| Betfair Exchange API | Börsenpreise, Tiefe, In-Play | nicht eingebunden; aus Deutschland nicht nutzbar |

## 6. Was jetzt zu tun ist

1. **Vier Wochen Logbuch laufen lassen.** Danach beantwortet
   `scripts/report_clv.py` die Frage, die kein Backtest beantworten kann: Haben
   die markierten Seiten den Schlusskurs geschlagen — getrennt nach
   Modell-Signal, Soft-Value und Prediction-Market-Abweichung?
2. **Linienstudie wöchentlich wiederholen** (`scripts/study_line_movement.py`)
   und die Richtung der Bewegung je Turnierklasse festhalten. Läuft die
   Linie systematisch zum Favoriten, ist früh wetten auf den Favoriten ein
   messbarer Edge; läuft sie nicht, ist das Thema erledigt.
3. **Nur dort wetten, wo der Preis erreichbar ist:** Broker-Bücher und
   GGL-Bücher nach Steuer. Prediction Markets bleiben Preisquelle.
4. **Keine Schwelle senken.** +5 % EV gegen einen scharfen Fairwert, sonst
   nichts — das Logbuch zeigt in einem Monat, ob selbst das reicht.
