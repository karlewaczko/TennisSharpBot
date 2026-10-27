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

## 4c. Polymarket und Kalshi: wie sharp — und wer dort gewinnt (25. Oktober 2026)

**Wie sharp die Kurse sind.** Jeder Dashboard-Lauf schreibt jetzt den Mittelkurs beider Börsen neben den fairen Pinnacle- oder Betfair-Preis (`data/processed/pm_gap_log.csv`, nachgetragen ab 22. Oktober). Über 408 Seiten liegt Polymarket im Median 0,8 Prozentpunkte daneben, Kalshi 0,5. In liquiden Märkten sind es bei beiden etwa 0,5 Punkte, die Spanne zwischen Geld und Brief beträgt typisch 2 Cent. Nach der Taker-Gebühr (Polymarket 5 % × p × (1−p), Kalshi 7 % × p × (1−p)) blieb keine Seite mit positivem Erwartungswert gegen den fairen Preis.

Polymarkets letzter Kurs vor dem Start, 2,049 entschiedene ATP- und WTA-Matches der letzten 30 Tage: Brier 0,201, der Favorit gewann 67 %. In keinem Preisband weicht die Siegquote mehr als 4,7 Punkte vom Kurs ab. Der größte Ausreißer betrifft Favoriten über 80 % auf der ersten Position: Kurs 88,4 %, gewonnen 93,1 % (n = 231). Auf der zweiten Position passt es genau (88,4 % gegen 88,8 %), es ist also eher Zufall als ein Muster. **Fazit: Beide Börsen sind bei ATP und WTA ungefähr so sharp wie Pinnacle.** Ihr Kurs hängt am Kurs der scharfen Buchmacher.

**Wo das Geld ist.** 413 Mio. $ Einsatz in 30 Tagen auf ATP- und WTA-Matches, davon 90 % während des Matches. Die 20 größten Wallets bewegen 45 % davon, und die allergrößten sind Live-Händler: RN1 setzte 18 Mio. $, 95 % davon live. Solche Positionen halten Sekunden und taugen nicht als Tipp.

**Wer die besten Tennis-Wetter sind.** Polymarket veröffentlicht jeden Trade mit Wallet und Profilnamen. `scripts/update_pm_traders.py` lädt alle Fills der entschiedenen Matches (2,053 Märkte, 20,556 Wallets) und misst für jede Wallet den Gewinn sowie den Closing Line Value ihrer Käufe vor dem Start, also den Abstand zum letzten Kurs vor Spielbeginn in Cent je Anteil. Sortiert wird nach der t-Statistik des CLV. Aufgenommen werden nur Wallets, die diese Bedingungen erfüllen:

- mindestens 20 Matches vor dem Start
- mindestens 2.000 $ Einsatz
- höchstens die Hälfte des Einsatzes live
- vor dem Start klar auf eine Seite (Market Maker enden flach und fliegen raus)

Das erfüllen 236 Wallets. Die zehn besten:

| # | Profil | Matches | Einsatz | Gewinn | ROI | CLV Ø | t |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | [UNEB3154s4f251](https://polymarket.com/profile/0x04641b57f332c15ecaa497799c55026d521967da) | 566 | 35.782 $ | +2.326 $ | 6,5 % | 1,4 ¢ | 5,1 |
| 2 | [0x99f0…9495](https://polymarket.com/profile/0x99f0d31fdced5b3a0e5ee2867730a6644a6c9495) | 1000 | 282.807 $ | +74.037 $ | 26,2 % | 0,7 ¢ | 4,6 |
| 3 | [bahn-cuon-baby](https://polymarket.com/profile/0x5cdc4e820fe30f22f3cf2581796d6e5abedc1f6b) | 509 | 14.350 $ | +873 $ | 6,1 % | 0,9 ¢ | 4,5 |
| 4 | [LeLynxMalynx](https://polymarket.com/profile/0x200ffb575b936d297fcf39076ddf2b476ae07a96) | 919 | 59.880 $ | +4.059 $ | 6,8 % | 0,8 ¢ | 3,7 |
| 5 | [arbbf](https://polymarket.com/profile/0x775efa2139f4c4706d56f077f2393b590411e94a) | 227 | 3.236 $ | +285 $ | 8,8 % | 1,3 ¢ | 3,7 |
| 6 | [MeistersApprenticeship](https://polymarket.com/profile/0xdc4f58a48ed4467743609fdce11eea483c759804) | 501 | 63.766 $ | +8.917 $ | 14,0 % | 0,8 ¢ | 3,5 |
| 7 | [mouzsynapse](https://polymarket.com/profile/0xa6ded03ba993d58d265dc8fa3f6ddda3d926256c) | 215 | 131.956 $ | −1.001 $ | −0,8 % | 1,3 ¢ | 3,4 |
| 8 | [atlantis.](https://polymarket.com/profile/0xa51c4289ad50956046dda8cd36afc25e33a72fde) | 32 | 3.606 $ | −106 $ | −2,9 % | 1,0 ¢ | 3,3 |
| 9 | [capitalpiston2](https://polymarket.com/profile/0x5e020e19bc4cc2cd24ab9b406604ee9df02ab178) | 765 | 33.466 $ | +2.533 $ | 7,6 % | 0,7 ¢ | 3,2 |
| 10 | [RadioFreeZerg](https://polymarket.com/profile/0x521070c99db06e54af5e8e4a91d6858decdfbd53) | 692 | 3.141 $ | +34 $ | 1,1 % | 0,6 ¢ | 3,1 |

Viele davon handeln Hunderte Matches im Monat mit kleinen Beträgen. Das sieht nach Modellen und Bots aus, nicht nach Bauchgefühl.

**Hält das Können?** Dafür wurde der Monat in zwei Hälften geteilt. Bei 632 Wallets mit je mindestens zehn Matches pro Hälfte korreliert der CLV der ersten Hälfte mit dem der zweiten zu 0,20. Das beste Zehntel der ersten Hälfte schlug den Schlusskurs danach um 0,3 Cent, der Durchschnitt lag bei -0,1 Cent. Die 20 Besten der ersten Hälfte kamen in der zweiten im Schnitt auf +1,4 Cent CLV je Wallet (+0,4 Cent nach Einsatz gewichtet) und gewannen zusammen 73.000 $ auf 253.000 $ Einsatz. Das ermutigt, aber eine Monatshälfte mit wenigen großen Wallets ist eine dünne Basis. Das Können ist echt, aber klein.

**Was das für uns heißt.** Den Profis blind zu folgen bringt nichts. Ihre offenen Positionen auf Partien der aktuellen Karte stehen jetzt im Dashboard, mit dem fairen Preis und der besten Buchquote daneben. Beim ersten Lauf (42 Positionen) lag der Erwartungswert der besten Buchquote im Median bei −4,0 %. Bei keiner der 25 Positionen mit Buchquote war er positiv. Wenn ein Profi drin ist, zahlt kein Buchmacher mehr als den fairen Preis. Jeder Lauf schreibt die Positionen der Top 20 nach `data/processed/pm_pro_positions_log.csv`. Mit den Schlussquoten aus `odds_snapshots.csv` lässt sich nach einigen Wochen messen, ob ihre Seite den Pinnacle-Schlusskurs schlägt. Erst dann wäre es ein Signal. **Kalshi** veröffentlicht Trades ohne Trader-Kennung, dort lässt sich niemand verfolgen.

## 4d. Fußball und Basketball (26. Oktober 2026)

Die Methode ist dieselbe wie beim Tennis: 30 Tage, Märkte ab 10.000 $ Volumen im Fußball und ab 5.000 $ im Basketball (`scripts/update_pm_traders.py --sport soccer|basketball`). Ein Fußballspiel besteht aus drei Ja/Nein-Märkten (Heim, Remis, Auswärts). Sie werden je Wallet zu einer Meinung über das Spiel zusammengefasst. Für die Rangliste gelten dieselben Bedingungen: 20 Spiele vor dem Anpfiff, 2.000 $ Einsatz, höchstens die Hälfte live und klare Richtung.

| | Fußball | Basketball |
|---|---:|---:|
| Spiele | 1.689 | 490 |
| Märkte | 3.576 | 490 |
| Wallets | 40.143 | 17.939 |
| Einsatz | 520 Mio. $ | 130 Mio. $ |
| davon live | 54 % | 69 % |
| Anteil der 20 größten Wallets | 37 % | 44 % |
| Wallets in der Rangliste | 817 | 143 |
| CLV-Korrelation zwischen den Monatshälften | 0,29 | 0,23 |
| bestes Zehntel in der zweiten Hälfte | +0,2 ¢ | +0,3 ¢ |
| Schnitt in der zweiten Hälfte | −0,2 ¢ | −0,3 ¢ |

**Fußball, die fünf besten:**

| # | Profil | Spiele | Einsatz | Gewinn | CLV Ø |
|---|---|---:|---:|---:|---:|
| 1 | [Kyn008](https://polymarket.com/profile/0xd29312e2446a746bbd94408e1c475f1ec6d7d683) | 174 | 1.411.523 $ | +12.527 $ | +1,2 ¢ |
| 2 | [omnibus-076daa](https://polymarket.com/profile/0x076daa87c4fe1a85402a9b6b8e0a866224388d4c) | 815 | 1.991.247 $ | −145.458 $ | +0,8 ¢ |
| 3 | [Takon88](https://polymarket.com/profile/0xa96274cc1b321afc8cbdc1ba07f7e2d471e6f7c8) | 40 | 1.254.758 $ | +166.241 $ | +2,4 ¢ |
| 4 | [Ne8om](https://polymarket.com/profile/0xbeb1c94b4260398f93f418e349a15a40b2ae4687) | 76 | 857.790 $ | −41.837 $ | +1,7 ¢ |
| 5 | [plonker2026](https://polymarket.com/profile/0x0a39b3b29ab3b7dd753aa96fde4ecab3f2dbb0b9) | 40 | 1.697.563 $ | −117.746 $ | +1,3 ¢ |

**Basketball, die fünf besten:**

| # | Profil | Spiele | Einsatz | Gewinn | CLV Ø |
|---|---|---:|---:|---:|---:|
| 1 | [BreakTheBank](https://polymarket.com/profile/0xf0318c32136c2db7fec88b84869aee6a1106c80c) | 22 | 5.136.992 $ | +968.777 $ | +0,7 ¢ |
| 2 | [TheComboConnoisseur](https://polymarket.com/profile/0x8314fd1f002a4e9bbf4b5abb939e24949a4e0f1e) | 37 | 14.382 $ | +2.966 $ | +3,5 ¢ |
| 3 | [bahn-cuon-baby](https://polymarket.com/profile/0x5cdc4e820fe30f22f3cf2581796d6e5abedc1f6b) | 134 | 2.742 $ | +2 $ | +1,3 ¢ |
| 4 | [0x9f15…bdb3](https://polymarket.com/profile/0x9f15613ebf1f36d4bc679e1211d1fc567cf9bdb3) | 23 | 65.334 $ | +32.260 $ | +1,8 ¢ |
| 5 | [monkeymashingkeyboard](https://polymarket.com/profile/0x684baa57c338c2549aec0aa3f034f695d72a8409) | 35 | 1.511.509 $ | +1.823 $ | +1,2 ¢ |

Was auffällt:

- **Hohe Einsätze vor dem Anpfiff.** Im Fußball setzen die Besten groß und fast nur vor dem Spiel: Kyn008 1,4 Mio. $ auf 174 Spiele, Takon88 1,25 Mio. $ auf 40.
- **Gewinn schwankt stark.** Mehrere Wallets mit klar positivem CLV haben im Monat sechsstellig verloren (omnibus-076daa −145.000 $, plonker2026 −118.000 $). Für den Gewinn ist ein Monat zu kurz, der CLV ist das bessere Maß.
- **Der größte Einzelwetter sitzt im Basketball.** BreakTheBank setzte 5,1 Mio. $ auf 22 Spiele und gewann 969.000 $.
- **Einige Profile tauchen in mehreren Sportarten oben auf:** TheComboConnoisseur, bahn-cuon-baby, Notradecopy, Deliles und no1dodgersfan. Das spricht für Modelle, die mehrere Sportarten abdecken.
- **Fazit wie beim Tennis.** Das Können ist echt und hält über den Monat, ist aber klein: Das beste Zehntel liegt danach etwa 0,4 bis 0,6 Cent je Anteil über dem Schnitt.
- **Keine Kalibrierung.** Für Fußball und Basketball steht hier keine Kalibrierung der Schlusskurse. Der Volumen-Filter zählt den Live-Handel mit, und der ist in Märkten, deren Ausgang eintritt, größer. Die Auswahl ist dadurch verzerrt.

## 4e. Korrektur: Gebühren, Glück und nur die Besten (27. Oktober 2026)

**Anlass.** Der Nutzer hat purplegatto geprüft, Platz 10 der Basketball-Liste im Profi-Radar. Auf Polymarket steht dieser Account insgesamt bei −1,97 Mio. $ bei 69 Mio. $ Volumen. Die Nachprüfung fand zwei Fehler in der Rangliste.

1. **Die Taker-Gebühr fehlte.** Polymarket berechnet Takern im Sport 0,05 × p × (1 − p) je Anteil, bei 50:50 also 1,25 Cent. purplegatto handelt nur als Taker. An einem NBA-Spiel lag unsere Rechnung um 232 $ unter Polymarkets eigener Positionsrechnung, und das waren genau die Gebühren. Ansonsten stimmte die Gewinnrechnung je Spiel mit Polymarket überein.
2. **Kein Schutz gegen Glück.** Unter Tausenden Wallets liegen einige allein durch Zufall vorn. Ein t-Wert von 2,4 reichte für Platz 10.

**Neu.** Für jeden Markt kommen die Taker-Fills aus Polymarkets `takerOnly`-Liste. Die Gebühr geht von Gewinn und CLV ab, gerankt wird nach dem t-Wert der CLV nach Gebühren. Beobachtet wird nur, wer **alle fünf Kriterien** erfüllt:

1. Vorsprung nach Gebühren, der eine Signifikanzprüfung besteht (Benjamini-Hochberg, höchstens 10 % Glückstreffer unter den Gelisteten)
2. Vorsprung in beiden Hälften der 30 Tage
3. Gewinn nach Gebühren in den 30 Tagen
4. Gewinn auf Polymarket über alle Märkte und die ganze Zeit (Leaderboard-API)
5. Mindestens 20 Spiele, 2.000 $ Einsatz, überwiegend vor dem Anpfiff und auf eine Seite

| | Rangliste | signifikant | + beide Hälften | + 30-Tage-Gewinn | + Gesamtgewinn |
|---|---:|---:|---:|---:|---:|
| Tennis | 225 | 11 | 11 | 7 | **6** |
| Fußball | 812 | 4 | 3 | 3 | **3** |
| Basketball | 162 | 4 | 2 | 2 | **2** |

**Die verbliebenen Wallets** (CLV nach Gebühren je Anteil, Gewinn nach Gebühren in 30 Tagen):

| Sportart | Profil | Spiele | CLV | t | Gewinn | Taker-Anteil | Polymarket gesamt |
|---|---|---:|---:|---:|---:|---:|---:|
| Tennis | [LeLynxMalynx](https://polymarket.com/profile/0x200ffb575b936d297fcf39076ddf2b476ae07a96) | 932 | +0,7 ¢ | 3,6 | +3.324 $ | 0 % | +43.274 $ / 10,8 Mio. $ |
| Tennis | [MeistersApprenticeship](https://polymarket.com/profile/0xdc4f58a48ed4467743609fdce11eea483c759804) | 509 | +0,6 ¢ | 3,1 | +8.681 $ | 0 % | +23.097 $ / 5,1 Mio. $ |
| Tennis | [capitalpiston2](https://polymarket.com/profile/0x5e020e19bc4cc2cd24ab9b406604ee9df02ab178) | 767 | +0,6 ¢ | 3,1 | +2.975 $ | 0 % | +13.076 $ / 2,5 Mio. $ |
| Tennis | [TuttyFruity](https://polymarket.com/profile/0x49b68438ae7db43a03d7ddaaceaef5581ac7d152) | 250 | +1,0 ¢ | 3,1 | +382 $ | 0 % | +401 $ / 0,1 Mio. $ |
| Tennis | [LuckyLoo](https://polymarket.com/profile/0x52d93dcf81444f793dda7fedc370f7a35101fb1a) | 66 | +1,8 ¢ | 2,8 | +20.912 $ | 0 % | +61.586 $ / 52,3 Mio. $ |
| Tennis | [0xc249…8a61](https://polymarket.com/profile/0xc2494b32d65dea3a3a80712589d10bc5733f8a61) | 123 | +1,9 ¢ | 2,6 | +1.424 $ | 0 % | +131.190 $ / 7,4 Mio. $ |
| Fußball | [Kyn008](https://polymarket.com/profile/0xd29312e2446a746bbd94408e1c475f1ec6d7d683) | 186 | +1,2 ¢ | 7,5 | +55.151 $ | 0 % | +75.715 $ / 5,5 Mio. $ |
| Fußball | [TheComboConnoisseur](https://polymarket.com/profile/0x8314fd1f002a4e9bbf4b5abb939e24949a4e0f1e) | 54 | +3,7 ¢ | 3,8 | +1.779 $ | 44 % | +50.800 $ / 1,9 Mio. $ |
| Fußball | [dacthenuac](https://polymarket.com/profile/0x10ff111022291d97966b415a779698312293ff77) | 174 | +1,1 ¢ | 3,4 | +371 $ | 0 % | +544 $ / 2,2 Mio. $ |
| Basketball | [monkeymashingkeyboard](https://polymarket.com/profile/0x684baa57c338c2549aec0aa3f034f695d72a8409) | 48 | +1,4 ¢ | 3,5 | +414.476 $ | 1 % | +784.599 $ / 28,6 Mio. $ |
| Basketball | [TheComboConnoisseur](https://polymarket.com/profile/0x8314fd1f002a4e9bbf4b5abb939e24949a4e0f1e) | 40 | +3,2 ¢ | 3,2 | +2.111 $ | 23 % | +50.800 $ / 1,9 Mio. $ |

Was die Korrektur zeigt:

- **Nach Gebühren verliert der Durchschnitt gegen den Schlusskurs.** Selbst das beste Zehntel der ersten Monatshälfte kommt in der zweiten nur auf etwa null (Tennis: Korrelation 0,35, bestes Zehntel danach +0,03 ¢, Schnitt −0,77 ¢ · Fußball: Korrelation 0,56, bestes Zehntel danach −0,23 ¢, Schnitt −1,09 ¢ · Basketball: Korrelation 0,20, bestes Zehntel danach −0,01 ¢, Schnitt −0,61 ¢).
- **Die meisten verbliebenen Profis sind Maker.** Sie stellen limitierte Orders ein und zahlen keine Gebühr. Ihr Vorteil entsteht beim Einstellen der Order. Wer ihnen später als Taker oder beim Buchmacher folgt, hat ihn nicht.
- **purplegatto** liegt nach Gebühren nirgends signifikant vorn: Basketball +0,27 Cent (t 0,75), Tennis −0,17 Cent, Fußball −0,66 Cent (t −3,5).
- **Abschnitte 4c und 4d** wurden vor dieser Korrektur gemessen. Ihre CLV-Werte sind vor Gebühren und ihre Listen ohne Signifikanzprüfung.

**Zweite Quelle: PolyInsider (27. Oktober 2026).** polyinsider.io wertet dieselben öffentlichen Polymarket-Daten unabhängig aus. Es zeigt je Trader den Gewinn über alle Märkte, das Volumen und die Trefferquote, dazu je Markt Wal-Wetten ab 5.000 $ und frische Wallets: Konten, deren erster Trade weniger als 24 Stunden alt ist, die nur diesen einen Markt gehandelt haben und dort mindestens 500 $ setzen.

Für die Elite-Liste muss ein Wallet seit diesem Tag auch bei PolyInsider insgesamt im Gewinn sein. Alle zehn sind es, und die Beträge stimmen mit Polymarket überein. Ein paar Beispiele:

- Kyn008: +76.000 $, Trefferquote 50 % über 420 Märkte
- monkeymashingkeyboard: +785.000 $, 53,8 % über 1.074 Märkte
- purplegatto zum Vergleich: −2,0 Mio. $, 48,9 % über 14.247 Märkte, im letzten Monat 44,5 %

Eine Trefferquote um 50 % ist bei Wetten nahe dem Münzwurf normal; was zählt, ist der Kurs, zu dem gekauft wird. Deshalb bleibt die CLV das Hauptkriterium.

Die PolyInsider-Seiten werden höflich gelesen: eine Seite alle zwei Sekunden, mit Projektnamen als Absender und nie die von robots.txt gesperrte `/api/`.

## 4f. PolyInsiders Rangliste geprüft (27. Oktober 2026)

**Was sie misst.** https://polyinsider.io/en/traders zeigt zwei Ranglisten, je die besten 25 nach Gewinn (vor Gebühren), für 24 Stunden, 7 Tage, 30 Tage und „all time“. „All time“ meint die Zeit, seit PolyInsider mitschreibt.

- **Whales:** Gewinn aus den Käufen ab 5.000 $ jedes Wallets.
- **Fresh wallets:** Gewinn aus den Wetten, die ein Wallet in seinen ersten 24 Stunden platziert hat.

**Die Whale-Liste der letzten 30 Tage:**

- **Geld:** +31,0 Mio. $ Gewinn auf 206 Mio. $ Einsatz.
- **Sportarten:** NFL 7, E-Sport 6, Fußball 5, Politik 3, Tennis 2, College-Football 1, NBA 1.
- **Überschneidung mit unserer Elite:** nur monkeymashingkeyboard (Basketball). Er steht dort in 24 Stunden auf Platz 4 (+310.000 $) und in 7 Tagen auf Platz 8 (+487.000 $).

**Warum die Liste keine Qualitätsliste ist.** Sie ist nach Gewinn sortiert und wählt damit die aus, die gewonnen haben. 55 der 59 Wallets auf den Whale-Listen gewannen öfter, als ihre Einstiegskurse erwarten ließen. Das folgt aus der Sortierung und ist für sich kein Beleg für Können. Zwei Beispiele:

- **joseph00677:** +5,8 Mio. $ aus 17 Wetten, gewann aber seltener, als die Kurse erwarten ließen (47 % gegenüber 56 %). Dazu kommen der größte Einzelverlust der Liste (−1,58 Mio. $ auf Chelsea) und, als frisches Wallet, ein Einzelgewinn von 1,2 Mio. $ auf Arsenal.
- **BreakTheBank:** +10,1 Mio. $ aus 224 Wetten, vor allem NFL und NBA, Trefferquote 56 % gegenüber 51 % Kurs. Im Basketball schlägt er den Schlusskurs nach Gebühren nur um 0,43 Cent (t 1,4); das reicht nicht als Nachweis.

**Die zwölf Whales aus Tennis, Fußball und Basketball nach unseren Kriterien.** Keiner besteht. Es gibt drei Gruppen:

- **Live-Händler:** ferrariChampions2026 (Tennis, 94 % live), RN1 (Tennis, 95 % live) und Flaznorp (Fußball, 80 % live und Market Maker). Ihr Vorteil entsteht während des Spiels und lässt sich nicht als Tipp vor dem Spiel nachspielen. RN1 hat vor dem Spiel sogar einen echten Vorsprung (+0,89 Cent nach Gebühren, t 4,1), setzt dort aber nur 5 % seines Geldes.
- **Gewinn trotz schlechter Kurse:** RichieRicher (−0,69 Cent, t −4,2) und nb1985 (−1,81 Cent, t −5,1) kaufen deutlich schlechter als der Schlusskurs. Ihr Gewinn ist Glück.
- **Zu wenig Siegwetten vor dem Anpfiff:** joseph00677, SmartPredictOrNot, raybanman, keeptheblueflagflyinghigh und Jsram (17 Spiele). Wir messen nur Siegwetten; Handicap- und Über/Unter-Wetten bleiben außen vor.

**Frische Wallets im Tennis, ein auffälliges Muster.** Fünf neue Konten setzten in ihren ersten 24 Stunden je eine große Wette auf eines von vier Matches unterer ATP-Ebenen, meist auf den Außenseiter, und gewannen alle:

| Wallet | Match | Einsatz | Kurs | Gewinn |
|---|---|---:|---:|---:|
| kalmal | Broady – Santillan (Guangzhou 2) | 33.800 $ | 34 % | +65.700 $ |
| lsiflsliggjriek | Cerundolo – Mensik (Shanghai) | 87.600 $ | 55 % | +71.800 $ |
| Frail-Ecosystem-Anagram | Domingues – Gakhov (Lissabon) | 34.700 $ | 35 % | +65.200 $ |
| Grigoralep | Domingues – Gakhov (Lissabon) | 17.800 $ | 25 % | +53.000 $ |
| kdvlklkvlsklkfs | Vallejo – Faria (Tokio, Quali) | 34.300 $ | 44 % | +43.700 $ |

Zwei der neuen Konten setzten auf dasselbe Challenger-Match in Lissabon, beide auf den Außenseiter. Das ist ein Muster und kein Beweis, wie PolyInsider selbst schreibt. Für diese Wallets taugt keine Rangliste, denn sie haben nur je eine Wette. Interessant wäre ein Alarm, sobald ein frisches Wallet auf ein anstehendes Match setzt; die Radar-Links führen zu PolyInsiders Marktseiten, wo solche Wetten erscheinen.

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
