# TennisSharpBot – Anleitung für Einsteiger

Diese Anleitung setzt **nichts** voraus außer: du kannst eine Datei
herunterladen und ein Programm installieren. Kein Programmieren, kein Git,
keine Kommandozeilen-Erfahrung nötig.

## ⚠️ Zuerst das Wichtigste: Dieses Modell schlägt die Buchmacher nicht

Das ist keine Vorsichtsformel, sondern ein **Messergebnis**. Der eingebaute
Prüf-Befehl (`python scripts/audit_edge.py`) rechnet es in drei Minuten nach:

- Pinnacles Quoten sind über 157.000 Datenpunkte auf **unter 1 Prozentpunkt**
  genau kalibriert. Da ist keine systematische Fehlbewertung zum Ausnutzen.
- Der entscheidende Test lautet: *Bringt unser Modell zusätzlich zur
  Buchmacher-Quote irgendeine Information?* Antwort über 13 Saisons und 55.124
  Spiele: **nein** — die Vorhersage wird mit unseren Merkmalen sogar minimal
  schlechter. Was wir wissen, weiß der Markt längst.
- Beim Bauen tauchte eine Strategie mit **+69 % Rendite** auf. Sie war
  wertlos: einmal, weil sie auf Quoten beruhte, die nie gleichzeitig
  buchbar waren, und einmal, weil sie statistisch reines Rauschen war. Beide
  Fallen werden jetzt automatisch erkannt.

**Was das Werkzeug wirklich gut kann:** Spielstärken einschätzen (Elo pro
Belag), Spielpläne und Quoten verfolgen, Head-to-Heads nachschlagen, Turniere
nach Platzgeschwindigkeit vergleichen — und dich davor bewahren, auf
Scheinmuster hereinzufallen. Nutze es zum Lernen und Beobachten.

Wenn du trotzdem wettest: In Deutschland gilt das LUGAS-Einzahlungslimit von
1.000 €/Monat, nur GGL-lizenzierte Anbieter sind rechtlich sauber, und setze
nie Geld ein, dessen Verlust dir wehtut.

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
4. **Automatischer Scan** (nur wenn du Schritte 1-3 alle ausgefüllt hast).
   Wenn du "j" wählst, durchsucht der Bot alle 4 Stunden von selbst nach
   Value-Bet-Kandidaten und schreibt dir automatisch bei neuen Treffern —
   du musst nicht mehr `/valuebets` fragen. Siehe Hinweis zum API-Budget
   unten.
5. **Ob auch die REST-API gestartet werden soll** (nur relevant, wenn du eine
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
| `/valuebets` | Quotenabweichungen zwischen Buchmachern (braucht Odds-API-Key) |

**Wichtig:** Direkt nach dem Start dauert es 1-2 Minuten, bis die Daten zum
ersten Mal vollständig geladen sind. Falls der Bot "not found"/"nicht
bereit" meldet, kurz warten und nochmal fragen.

**Zu `/valuebets`:** Das listet Spiele auf, bei denen ein Buchmacher deutlich
von den anderen abweicht. Das ist ein *Beobachtungs*-Signal, keine
Wettempfehlung — laut der Messung oben reicht es nicht für einen echten
Vorteil.

**Automatischer Scan (falls aktiviert):** Der Bot meldet sich von selbst,
sobald er neue Kandidaten findet — kein `/valuebets` mehr nötig. Jede
Kombination aus Spieler/Gegner/Buchmacher wird nur einmal gemeldet, nicht bei
jedem Durchlauf erneut. Nachträglich einstellen/ändern: in `config/.env` die
Zeile `TELEGRAM_VALUEBETS_INTERVAL_MINUTES` bearbeiten (Minuten zwischen zwei
Scans, `0` = aus) und danach `docker compose up -d --build bot` ausführen.
**Achtung Kostenkontrolle:** kostenlose Odds-API-Keys sind auf ca. 500
Anfragen/Monat begrenzt; alle 4 Stunden (Standard) verbraucht davon grob ein
Viertel, kürzere Intervalle entsprechend mehr.

Behandle es als "hier lohnt sich ein zweiter Blick", nicht als
"hier ist Geld zu holen".

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
