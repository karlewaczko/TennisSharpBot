# TennisSharpBot – Anleitung für Einsteiger

Diese Anleitung setzt **nichts** voraus außer: du kannst eine Datei
herunterladen und ein Programm installieren. Kein Programmieren, kein Git,
keine Kommandozeilen-Erfahrung nötig.

⚠️ **Wichtig, bevor du startest:** Das hier ist ein Recherche-Werkzeug, keine
Gelddruckmaschine. Die eingebauten Backtests zeigen selbst mit einem
ordentlichen Modell einen Verlust gegen Pinnacle (siehe README, Abschnitt
"Honest backtest result"). Nutze es zum Lernen und Beobachten, nicht als
Freibrief zum Wetten. In Deutschland gilt außerdem das LUGAS-Einzahlungslimit
von 1.000 €/Monat, und nur GGL-lizenzierte Anbieter sind rechtlich sauber.

## Was du am Ende hast

Einen Telegram-Bot, den du wie einen Chat-Partner fragen kannst:
- "Zeig mir die aktuelle Weltrangliste (Elo)"
- "Was steht heute auf dem Spielplan?"
- "Wie steht der Head-to-Head zwischen zwei Spielern?"
- "Gibt es aktuell Value Bets?" (optional, braucht einen zusätzlichen Gratis-Key)

Die Daten aktualisieren sich automatisch einmal täglich im Hintergrund.

## Schritt 1: Docker Desktop installieren

Docker ist das Programm, das die ganze Technik im Hintergrund für dich
laufen lässt, ohne dass du Python oder sonst was installieren musst.

- **Windows/Mac:** [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
  herunterladen, installieren, einmal starten (Symbol in der Taskleiste/im
  Dock erscheint, wenn es läuft).
- **Linux:** `sudo apt install docker.io docker-compose-plugin` (oder die
  Anleitung für deine Distribution).

Docker Desktop fragt bei der Installation eventuell nach einem Neustart des
Rechners — das ist normal, einmal machen und danach weiter.

## Schritt 2: Projekt herunterladen

**Ohne Kommandozeile (am einfachsten):**
1. Öffne im Browser:
   `https://github.com/karlewaczko/TennisSharpBot/archive/refs/heads/claude/tennis-betting-model-data-wze73q.zip`
2. Die ZIP-Datei entpacken (Rechtsklick → "Extrahieren"/"Entpacken").
3. Den entpackten Ordner an einen Ort legen, den du wiederfindest (z. B. Desktop).

**Mit Kommandozeile (falls du Git installiert hast):**
```bash
git clone https://github.com/karlewaczko/TennisSharpBot.git
cd TennisSharpBot
git checkout claude/tennis-betting-model-data-wze73q
```

## Schritt 3: Einrichtungs-Skript ausführen

Im entpackten/geklonten Ordner:

- **Windows:** Rechtsklick auf `quickstart.ps1` → "Mit PowerShell ausführen".
  Falls eine Sicherheitswarnung ("nicht signiertes Skript") erscheint: in der
  geöffneten PowerShell einmalig eingeben
  `Set-ExecutionPolicy -Scope Process Bypass` und Enter drücken, dann das
  Skript erneut starten.
- **Mac/Linux:** Terminal im Projektordner öffnen und eingeben:
  ```bash
  ./quickstart.sh
  ```
  (Falls "Permission denied" kommt: vorher einmal `chmod +x quickstart.sh` ausführen.)

Das Skript fragt dich der Reihe nach:

1. **Telegram-Bot-Token.** Dafür in Telegram nach **@BotFather** suchen, ihm
   `/newbot` schicken, einen Namen vergeben — er gibt dir einen Token
   (eine lange Zeichenfolge). Den hier einfügen.
2. **Chat-ID** (optional, für eine tägliche automatische Nachricht). Kann man
   überspringen (einfach Enter drücken).
3. **Odds-API-Key** (optional, nur für die Value-Bet-Funktion). Kostenlos auf
   [the-odds-api.com](https://the-odds-api.com) registrieren, Key kopieren,
   oder überspringen.
4. **Ob auch die REST-API gestartet werden soll** (nur relevant, wenn du eine
   eigene App bauen willst — für den reinen Telegram-Bot einfach "N"/Enter).

Danach baut und startet das Skript alles automatisch. Das dauert beim
allerersten Mal ein paar Minuten (lädt Software-Pakete herunter).

## Schritt 4: Bot benutzen

In Telegram deinen Bot suchen (den Namen, den du bei BotFather vergeben
hast) und `/start` schicken. Er antwortet mit allen verfügbaren Befehlen:

| Befehl | Was er macht |
|---|---|
| `/rankings atp` | Aktuelle Elo-Weltrangliste Herren |
| `/rankings wta` | Aktuelle Elo-Weltrangliste Damen |
| `/surface` | Schnellste Turniere der aktuellen Saison |
| `/surface Wimbledon` | Speed-Rating für ein bestimmtes Turnier |
| `/upcoming atp` | Anstehende Spiele + Quoten |
| `/h2h Djokovic Nadal` | Direktvergleich zweier Spieler (aus dem aktuellen Spielplan) |
| `/valuebets` | Aktuelle Value-Bet-Kandidaten (braucht Odds-API-Key) |

**Wichtig:** Direkt nach dem Start dauert es 1-2 Minuten, bis die Daten zum
ersten Mal vollständig geladen sind. Falls der Bot "not found"/"nicht
bereit" meldet, kurz warten und nochmal fragen.

## Alles wieder stoppen

Im Projektordner:
```bash
docker compose down
```
Das beendet alles, ohne etwas zu löschen — mit `docker compose up -d` (ohne
`--build`) startest du später alles wieder in Sekunden.

## Logs ansehen (falls etwas nicht klappt)

```bash
docker compose logs -f
```
Zeigt live, was die einzelnen Programmteile gerade tun. Mit `Strg+C` beenden
(das stoppt nur die Anzeige, nicht den Bot selbst).

## Problemlösung

- **"Docker wurde nicht gefunden"** → Docker Desktop ist nicht installiert
  oder nicht im Suchpfad. Neu installieren, Rechner ggf. neu starten.
- **"Docker läuft gerade nicht"** → Docker Desktop öffnen (Symbol anklicken)
  und warten, bis es "Running" anzeigt, dann Skript erneut starten.
- **Bot antwortet gar nicht** → `docker compose logs bot` ansehen. Häufigster
  Grund: falscher/fehlender Token in `config/.env`.
- **"ODDS_API_KEY ist nicht gesetzt"** bei `/valuebets` → normal, wenn du
  Schritt 3.3 übersprungen hast. Key nachträglich in `config/.env` eintragen
  und `docker compose up -d --build bot` erneut ausführen.
- **Ich will von vorn anfangen** → `docker compose down -v` (löscht auch die
  gespeicherten Daten) und `./quickstart.sh` bzw. `./quickstart.ps1` erneut
  ausführen.

## Technische Details

Für alles, was über diese Einsteiger-Anleitung hinausgeht (wie die Daten
genau verarbeitet werden, welche Quellen genutzt werden, wie man das Modell
selbst weiterentwickelt), siehe `README.md` im selben Ordner.
