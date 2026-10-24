# Prüfung fremder Datenquellen und Modelle (2026-09-04)

Fünf vom Nutzer vorgeschlagene Quellen, gegen den Ist-Zustand gemessen.

## Kurzfassung

Keine der Quellen macht das Modell marktschlagend. Zwei unabhängige Belege:

| Messung | Modell | Markt | Abstand |
|---|---|---|---|
| Dieses Repo, `audit_edge.py`, 55 124 Partien | Log-Loss 0.61869 | 0.59408 | Informationsgewinn **−0.00111** |
| nickdatak, XGBoost, 8 224 Partien ab 2023 | Brier 0.2162 | Betfair 0.1988 | **−0.016 bis −0.017** |

Zwei getrennt entwickelte Codebasen mit derselben Feature-Klasse (Elo,
Surface-Elo, Form, H2H, Ermüdung, Tier) verlieren beide gegen den Markt,
in derselben Größenordnung. Das ist kein Implementierungsfehler, sondern
die Eigenschaft eines effizienten Marktes.

Eine Quelle ist trotzdem klar besser als unsere und behebt einen realen
Defekt, den wir seit Tagen mitschleppen.

## stats.tennismylife.org — deutlich besser als unsere Historie

Sackmann-Schema, 50 Spalten, MIT-Lizenz, tägliche Aktualisierung,
CSV + REST-API (`/api/data-files`, aus diesem Container erreichbar).

Gemessen für 2026:

| | tennis-data.co.uk (aktuell) | TennisMyLife |
|---|---|---|
| Partien 2026 | 3 971 | **10 439** (2.6x) |
| Spieler mit Partien 2026 | 556 | **1 263** |
| Ebenen | ATP+WTA Haupttour | + Challenger, + ATP-Quali |
| Aufschlag/Return pro Match | **keine** | **99.3 %** der Partien |
| Quoten | ja | nein |

Aufschlagfelder: ace, df, svpt, 1stIn, 1stWon, 2ndWon, SvGms, bpSaved,
bpFaced — je Spieler. Dazu indoor, draw_size, tourney_level, Größe,
Hand, Alter, Spieldauer.

### Der Defekt, den das behebt

`LiveState.is_stale` markiert Zeilen, deren Pausen- und Formwerte eine
Lücke im Feed beschreiben statt den Spieler. Betroffen waren zeitweise
27 von 48 Modellzeilen. Ursache ist die fehlende Challenger- und
Quali-Abdeckung:

| Spieler | unser Feed 2026 | TennisMyLife 2026 |
|---|---|---|
| Smith C. | 1 Partie, letzte 31.03. | **84 Partien, letzte 28.08.** |
| Bergs Z. | veraltet | 43 Partien, letzte 17.08. |
| Rakhimova K. | veraltet | 24 Partien, letzte 13.08. |

## Die übrigen vier

- **tennis-data.co.uk** — bereits unsere Quelle. Einziger Lieferant von
  Quoten (Pinnacle, bet365, Max, Avg) und deshalb unverzichtbar, egal
  was sonst dazukommt. Ein Join bleibt nötig.
- **mcekovic/tennis-crystal-ball** — ernsthaftes Java/PostgreSQL-Projekt
  auf Sackmann-Daten, neuronales Netz, 100+ Statistikkategorien. Keine
  veröffentlichte Genauigkeitsmessung, kein Quotenbacktest. Als
  Ideengeber für Features nützlich, nicht als Beleg.
- **nickdatak/Tennis-Match-Predictions** — der wertvollste Fund, aber
  nicht als Vorbild: er misst sauber gegen Betfair und **verliert**.
  Siehe Tabelle oben.
- **gmalbert/tennis-predictions** — verknüpft genau die beiden Quellen,
  die auch wir brauchen (TennisMyLife + tennis-data.co.uk), mit 81.5 %
  Trefferquote beim Namensabgleich. Keine Genauigkeits- oder ROI-Zahlen
  veröffentlicht.

## Was fehlen würde, um den Markt zu schlagen

Keine der fünf Quellen enthält Information, die der Markt nicht schon
hat. Was fehlt, ist entweder schneller (Verletzungen, Aufgabe im
Aufwärmen, Wetter, Platzgeschwindigkeit am Tag) oder feiner
(Punkt-für-Punkt-Daten, z. B. Sackmanns Match Charting Project — in
TennisMyLife nicht enthalten).
