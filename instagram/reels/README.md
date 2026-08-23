# Reel 01 – "Warum der S&P ständig genau hier dreht" (Gamma-Wall)

| Datei | Was |
|---|---|
| `reel_01_gamma.mp4` | **Das fertige Reel.** 1080×1920, H.264, 30 fps, 32 s, ~1,9 MB |
| `cover_01_gamma.png` | Reel-Cover 1080×1350 (= dein Grid-Bild) |
| `reel_01_gamma.html` | Die Quelle – hier änderst du Text, Timing, Farben |
| `cover_01_gamma.html` | Quelle des Covers |
| `fonts.css` | Archivo Black / Inter / JetBrains Mono, eingebettet (offline-fähig) |
| `tools/build.sh` | Rendert HTML → MP4 in einem Befehl |

## Warum genau dieses Thema

Es ist der Post, der deine Positionierung in 32 Sekunden beweist: Er zeigt eine
Mechanik, die in Deutschland fast niemand erklärt, braucht keine Kursprognose
(also kein § 85 WpHG-Risiko) und ist gleichzeitig für Anfänger verständlich.
Genau das Profil aus `../00_STRATEGIE.md`, Säule 1.

## Aufbau (Timing)

| Zeit | Beat | Bild |
|---|---|---|
| 0,0–3,6 s | **Hook** "Der S&P dreht ständig genau hier." | Kurslinie zeichnet sich auf, prallt am Level ab |
| 3,6–6,6 s | Open Loop: "Kein Zufall. Kein Widerstand." | Level-Linie steht |
| 6,6–11,8 s | "An diesem Strike liegen Millionen." | Open-Interest-Balken fahren ein |
| 11,8–17,4 s | "Market Maker halten dagegen." | zwei Hedging-Karten |
| 17,4–22,2 s | "Nicht aus Meinung. Sondern um neutral zu bleiben." | Karten bleiben |
| 22,2–26,6 s | "Das Ergebnis: Der Kurs klebt." | rotes Band kollabiert auf das Level |
| 26,6–30,0 s | "Diese Zahl steht jeden Morgen fest." | – |
| 30,0–32,0 s | **CTA + Loop** "Dein Broker zeigt sie dir nur nicht." | Speichern-Hinweis |

Der letzte Frame führt visuell zum ersten zurück → **Rewatches zählen als Watch
Time** (siehe `../01_ALGORITHMUS.md`, Hebel 4).

## Was noch fehlt: deine Stimme

Das Video ist so postbar. Aber der Algorithmus bevorzugt 2026 **Original-Audio**,
und deine Stimme ist der Teil, den keine Software liefern kann. Nimm das Sprecher-
skript mit dem Handy auf (3 Minuten Aufwand) und lege es in CapCut über das MP4:

```
0,0 s   Der S&P dreht seit Wochen ständig an derselben Stelle.
3,6 s   Das ist kein Zufall – und es ist auch kein Widerstand.
6,6 s   An diesem Strike liegen Millionen an offenen Optionen.
11,8 s  Und die Market Maker auf der Gegenseite halten dagegen.
17,4 s  Nicht aus Meinung. Sondern nur, um delta-neutral zu bleiben:
        Steigt der Kurs, verkaufen sie. Fällt er, kaufen sie.
22,2 s  Das Ergebnis: Der Kurs klebt an dieser Zahl.
26,6 s  Und diese Zahl steht jeden Morgen vor der Eröffnung fest.
30,0 s  Dein Broker zeigt sie dir nur nicht. Speicher dir das.
```

Sprechtempo ~2,7 Wörter/Sekunde, keine Pause vor dem ersten Wort – du startest
direkt im Satz.

## Caption für den Post

```
Der S&P dreht ständig an derselben Zahl. Das ist keine Charttechnik.

An Strikes mit sehr hohem Open Interest sind Market Maker häufig long Gamma.
Um delta-neutral zu bleiben, verkaufen sie in steigende Kurse und kaufen in
fallende. Genau das dämpft die Bewegung – der Kurs "klebt" am Level.

Deshalb sehen runde Zahlen wie Magnete aus. Sie sind aber nur die Nebenwirkung
davon, wie jemand anders sein Risiko absichert.

Welche Zahl klebt bei dir gerade im Chart? Schreib sie in die Kommentare.

Speicher dir das – beim nächsten Verfallstag brauchst du es.

⚠️ Keine Anlageberatung. Keine Kauf- oder Verkaufsempfehlung.
Optionen können zum Totalverlust führen.

#optionshandel #gamma #spx #optionsstrategie #interactivebrokers
```

**Posten:** Di–Do, 19:00–22:00 (Hauptslot Reels). Eigenes Cover setzen
(`cover_01_gamma.png`), Untertitel sind bereits im Bild.

## Fachlicher Hinweis

Die Aussage gilt für den **Long-Gamma-Fall** der Händler auf der Gegenseite –
dann wird Volatilität gedämpft und der Kurs pinnt. Bei **negativem Dealer-Gamma**
dreht sich der Effekt um und Bewegungen werden verstärkt. Das ist bewusst ein
eigenes zweites Reel wert ("Was passiert, wenn Gamma negativ wird") – ein
perfekter Serien-Anschluss.

## Neu rendern / Thema ändern

```bash
# 1. Text ändern: im HTML den Array BEATS bearbeiten
#    Format: [start, ende, 'Zeile 1', 'Zeile 2 mit <span class="hi">Highlight</span>', 'KICKER']
#    Die Schriftgröße passt sich automatisch an (fit()).
# 2. Rendern:
./tools/build.sh reel_01_gamma
```

Dauer: ~60 s Frames + ~30 s Encoding. Voraussetzungen: `node`,
`playwright-core`, Chromium unter `/opt/pw-browsers`, `pip install imageio-ffmpeg`.

**Vorschau einzelner Zeitpunkte** (schneller als voll rendern):
`node tools/preview.js` – legt einen Kontaktbogen unter `/tmp/preview.png` ab.

---

# Reel 02 – "Optionsschein ist keine Option" (Creator Bright)

Gleiche Pipeline, **Stil nach Flo-Pharell-Vorbild**: weiß statt dunkel, Anton in
Versalien, gelbes Marker-Highlight, harte Rot/Grün-Kontraste, Bullen-Mark oben
links. Details zum Stilsystem in `../03_BRANDING.md`.

| Datei | Was |
|---|---|
| `reel_02_optionsschein.mp4` | **Fertiges Reel.** 1080×1920, H.264, 30 fps, 30 s, ~1,6 MB |
| `cover_02_optionsschein.png` | Cover 1080×1350 im Thumbnail-Stil |
| `reel_02_optionsschein.html` | Quelle |
| `fonts_bright.css` | Anton + Inter, eingebettet |

## Warum dieses Thema

Es ist die häufigste Verwechslung deutscher Privatanleger und trifft deine
Kernzielgruppe direkt: Wer bei einem Neobroker "Optionsschein" kauft, glaubt,
er handle Optionen. Der Post erklärt den Unterschied, ist **faktisch und ohne
jede Kursprognose** – und führt logisch zum Broker-Content (Säule 6).

## Aufbau (9 Beats, ~3 s Takt)

| Zeit | Aussage |
|---|---|
| 0,0–2,9 | **Hook:** "Optionsschein ist keine Option." |
| 2,9–5,6 | "Und der Unterschied kostet dich Geld." |
| 5,6–12,8 | Schein = Produkt der Bank / Option = Kontrakt an der Börse |
| 12,8–20,2 | Wer stellt den Preis: Bank vs. Markt |
| 20,2–27,0 | Nur die Option kannst du verkaufen → Prämie |
| 27,0–30,0 | **CTA:** "Dein Neobroker hat nur die falsche." + Speichern |

Ab Sekunde 12,8 wandert die Headline nach oben und die Vergleichstabelle füllt
sich Zeile für Zeile mit – das ist der **Save-Auslöser**.

## Sprecherskript

```
0,0 s   Ein Optionsschein ist keine Option.
2,9 s   Und der Unterschied kostet dich richtig Geld.
5,6 s   Der Schein ist ein Produkt der Bank.
9,2 s   Die Option ist ein Kontrakt an der Börse.
12,8 s  Beim Schein stellt die Bank den Preis.
16,6 s  Bei der Option macht das der Markt.
20,2 s  Und nur eine davon kannst du verkaufen.
23,8 s  Nur damit kassierst du Prämie statt sie zu zahlen.
27,0 s  Dein Neobroker hat nur die falsche. Speicher dir das.
```

## Caption

```
Optionsschein ≠ Option. Der Unterschied kostet die meisten Anleger Geld.

Der Optionsschein ist ein Wertpapier, das eine Bank herausgibt. Sie stellt den
Preis, und du trägst ihr Emittentenrisiko.

Die Option ist ein standardisierter Kontrakt an einer Terminbörse. Der Preis
entsteht am Markt, dahinter steht ein Clearinghaus.

Der entscheidende Punkt: Eine Option kannst du auch verkaufen und dafür Prämie
kassieren. Beim Schein bist du immer der, der zahlt.

Welchen der beiden hast du zuletzt gehandelt? Schreib es in die Kommentare.

⚠️ Keine Anlageberatung. Derivate können zum Totalverlust führen.

#optionshandel #optionsschein #derivate #optionsstrategie #interactivebrokers
```

## Rendern

```bash
export NODE_PATH=$(npm root -g)      # oder lokales node_modules mit playwright-core
./tools/build.sh reel_02_optionsschein
```

`render.js` liest die Länge aus `window.DUR` – neue Reels können also beliebig
lang sein, ohne dass du das Skript anfassen musst.
