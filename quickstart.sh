#!/bin/bash
# One-command setup for TennisSharpBot (Telegram bot + optional REST API).
# For macOS/Linux. Windows users: use quickstart.ps1 instead.
#
# What this does:
#   1. Checks Docker is installed and running.
#   2. Asks a few questions (Telegram bot token, etc.) and writes config/.env.
#   3. Builds and starts the containers with `docker compose up -d --build`.
# You do not need Python, git knowledge, or any prior setup beyond Docker.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
info() { printf '  %s\n' "$1"; }
warn() { printf '\033[33m! %s\033[0m\n' "$1"; }
ok()   { printf '\033[32m✓ %s\033[0m\n' "$1"; }

bold "TennisSharpBot -- Einrichtung"
echo

# --- 1. Docker check -------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    warn "Docker wurde nicht gefunden."
    info "Bitte zuerst Docker Desktop installieren: https://www.docker.com/products/docker-desktop/"
    info "Danach dieses Skript erneut ausführen: ./quickstart.sh"
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    warn "Docker ist installiert, läuft aber gerade nicht."
    info "Bitte Docker Desktop starten (Symbol im Dock/Taskleiste) und dann erneut versuchen."
    exit 1
fi
ok "Docker gefunden und läuft."
echo

# --- 2. Questions ------------------------------------------------------------
ENV_FILE="config/.env"
mkdir -p config

if [ -f "$ENV_FILE" ]; then
    warn "Es existiert bereits eine config/.env."
    read -r -p "Überschreiben und neu einrichten? (j/N): " OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[jJ] ]]; then
        info "Bestehende Konfiguration wird beibehalten, starte Container..."
        SKIP_QUESTIONS=1
    fi
fi

if [ -z "${SKIP_QUESTIONS:-}" ]; then
    bold "Telegram-Bot (empfohlen)"
    info "1. Öffne Telegram, suche nach '@BotFather' und schreibe ihm."
    info "2. Schicke ihm /newbot und folge den Anweisungen (Name + Nutzername für deinen Bot wählen)."
    info "3. BotFather schickt dir einen Token, der so aussieht: 123456789:AAExampleTokenXYZ"
    echo
    read -r -p "Telegram-Bot-Token einfügen (oder Enter zum Überspringen): " TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID=""
    if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        echo
        info "Optional: tägliche Rangliste automatisch an einen Chat schicken."
        info "Schick deinem Bot jetzt kurz eine beliebige Nachricht in Telegram, dann Enter drücken."
        read -r -p "  (Enter wenn erledigt, oder direkt weiter mit Enter zum Überspringen) " _
        info "Öffne in einem Browser: https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"
        info "Suche dort nach \"chat\":{\"id\":...} und kopiere die Zahl."
        read -r -p "Chat-ID einfügen (oder Enter zum Überspringen): " TELEGRAM_CHAT_ID
    fi

    echo
    bold "Live Value Bets (optional)"
    info "Braucht einen kostenlosen Key von https://the-odds-api.com -- ohne Key funktioniert"
    info "alles andere (Ranglisten, Spielplan, Head-to-Head) trotzdem ganz normal."
    read -r -p "Odds-API-Key einfügen (oder Enter zum Überspringen): " ODDS_API_KEY

    VALUEBETS_INTERVAL=0
    if [ -n "$ODDS_API_KEY" ] && [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        echo
        info "Der Bot kann selbstständig alle paar Stunden nach Value Bets suchen und"
        info "dir bei neuen Kandidaten von sich aus schreiben (statt dass du /valuebets"
        info "fragen musst). Achtung: kostenlose Odds-API-Keys sind auf ca. 500"
        info "Anfragen/Monat begrenzt -- alle 4 Stunden verbraucht davon ca. 1/4."
        read -r -p "Automatischen Scan aktivieren? (j/N): " AUTO_SCAN
        if [[ "$AUTO_SCAN" =~ ^[jJ] ]]; then
            VALUEBETS_INTERVAL=240
        fi
    fi

    echo
    read -r -p "Auch die REST-API starten, z.B. für eine eigene App? (j/N): " START_API
    START_API_FLAG="nein"
    [[ "$START_API" =~ ^[jJ] ]] && START_API_FLAG="ja"

    cat > "$ENV_FILE" <<EOF
TOURS=atp,wta
START_SEASON=2010
ODDS_API_KEY=${ODDS_API_KEY}
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
TELEGRAM_DIGEST_HOUR_UTC=7
TELEGRAM_VALUEBETS_INTERVAL_MINUTES=${VALUEBETS_INTERVAL}
TELEGRAM_VALUEBETS_EDGE_THRESHOLD=0.03
EOF
    ok "config/.env geschrieben."
    echo "$START_API_FLAG" > .quickstart_start_api
fi

# --- 3. Start containers ----------------------------------------------------
echo
bold "Container werden gebaut und gestartet (das kann beim ersten Mal ein paar Minuten dauern)..."

SERVICES="updater"
if [ -s "$ENV_FILE" ] && grep -q "^TELEGRAM_BOT_TOKEN=.\+" "$ENV_FILE"; then
    SERVICES="$SERVICES bot"
fi
if [ -f .quickstart_start_api ] && grep -qi "^ja$" .quickstart_start_api; then
    SERVICES="$SERVICES api"
fi
rm -f .quickstart_start_api

docker compose up -d --build $SERVICES

echo
ok "Fertig! Läuft im Hintergrund."
echo
if [[ "$SERVICES" == *bot* ]]; then
    info "-> Öffne Telegram, suche deinen Bot und schicke ihm /start"
fi
if [[ "$SERVICES" == *api* ]]; then
    info "-> API-Doku im Browser: http://localhost:8000/docs"
fi
info "-> Logs ansehen:   docker compose logs -f"
info "-> Alles stoppen:  docker compose down"
echo
warn "Hinweis: Keine Finanz-/Wettberatung. Nur Recherche-Signal, keine Garantie."
