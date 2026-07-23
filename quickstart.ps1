# One-command setup for TennisSharpBot (Telegram bot + optional REST API).
# For Windows (PowerShell). macOS/Linux users: use ./quickstart.sh instead.
#
# What this does:
#   1. Checks Docker Desktop is installed and running.
#   2. Asks a few questions (Telegram bot token, etc.) and writes config/.env.
#   3. Builds and starts the containers with `docker compose up -d --build`.
# You do not need Python, git knowledge, or any prior setup beyond Docker.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Bold($msg) { Write-Host $msg -ForegroundColor White }
function Write-Info($msg) { Write-Host "  $msg" }
function Write-Warn($msg) { Write-Host "! $msg" -ForegroundColor Yellow }
function Write-Ok($msg)   { Write-Host ("+ " + $msg) -ForegroundColor Green }

Write-Bold "TennisSharpBot -- Einrichtung"
Write-Host ""

# --- 1. Docker check ---------------------------------------------------------
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Write-Warn "Docker wurde nicht gefunden."
    Write-Info "Bitte zuerst Docker Desktop installieren: https://www.docker.com/products/docker-desktop/"
    Write-Info "Danach dieses Skript erneut ausfuehren: ./quickstart.ps1"
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Docker ist installiert, laeuft aber gerade nicht."
    Write-Info "Bitte Docker Desktop starten und dann erneut versuchen."
    exit 1
}
Write-Ok "Docker gefunden und laeuft."
Write-Host ""

# --- 2. Questions -------------------------------------------------------------
$envFile = "config/.env"
New-Item -ItemType Directory -Force -Path "config" | Out-Null
$skipQuestions = $false

if (Test-Path $envFile) {
    Write-Warn "Es existiert bereits eine config/.env."
    $overwrite = Read-Host "Ueberschreiben und neu einrichten? (j/N)"
    if ($overwrite -notmatch '^[jJ]') {
        Write-Info "Bestehende Konfiguration wird beibehalten, starte Container..."
        $skipQuestions = $true
    }
}

$startApiFlag = $false

if (-not $skipQuestions) {
    Write-Bold "Telegram-Bot (empfohlen)"
    Write-Info "1. Oeffne Telegram, suche nach '@BotFather' und schreibe ihm."
    Write-Info "2. Schicke ihm /newbot und folge den Anweisungen (Name + Nutzername waehlen)."
    Write-Info "3. BotFather schickt dir einen Token, der so aussieht: 123456789:AAExampleTokenXYZ"
    Write-Host ""
    $telegramToken = Read-Host "Telegram-Bot-Token einfuegen (oder Enter zum Ueberspringen)"
    $telegramChatId = ""
    if ($telegramToken) {
        Write-Host ""
        Write-Info "Optional: taegliche Rangliste automatisch an einen Chat schicken."
        Write-Info "Schick deinem Bot jetzt kurz eine beliebige Nachricht in Telegram."
        Read-Host "  (Enter wenn erledigt, oder direkt Enter zum Ueberspringen)" | Out-Null
        Write-Info "Oeffne im Browser: https://api.telegram.org/bot$telegramToken/getUpdates"
        Write-Info 'Suche dort nach "chat":{"id":...} und kopiere die Zahl.'
        $telegramChatId = Read-Host "Chat-ID einfuegen (oder Enter zum Ueberspringen)"
    }

    Write-Host ""
    Write-Bold "Live Value Bets (optional)"
    Write-Info "Braucht einen kostenlosen Key von https://the-odds-api.com -- ohne Key funktioniert"
    Write-Info "alles andere (Ranglisten, Spielplan, Head-to-Head) trotzdem ganz normal."
    $oddsApiKey = Read-Host "Odds-API-Key einfuegen (oder Enter zum Ueberspringen)"

    Write-Host ""
    $startApi = Read-Host "Auch die REST-API starten, z.B. fuer eine eigene App? (j/N)"
    $startApiFlag = $startApi -match '^[jJ]'

    @"
TOURS=atp,wta
START_SEASON=2010
ODDS_API_KEY=$oddsApiKey
TELEGRAM_BOT_TOKEN=$telegramToken
TELEGRAM_CHAT_ID=$telegramChatId
TELEGRAM_DIGEST_HOUR_UTC=7
"@ | Set-Content -Path $envFile -Encoding utf8

    Write-Ok "config/.env geschrieben."
}

# --- 3. Start containers ------------------------------------------------------
Write-Host ""
Write-Bold "Container werden gebaut und gestartet (das kann beim ersten Mal ein paar Minuten dauern)..."

$services = @("updater")
$envContent = Get-Content $envFile -Raw
if ($envContent -match "TELEGRAM_BOT_TOKEN=.+") { $services += "bot" }
if ($startApiFlag) { $services += "api" }

docker compose up -d --build @services

Write-Host ""
Write-Ok "Fertig! Laeuft im Hintergrund."
Write-Host ""
if ($services -contains "bot") {
    Write-Info "-> Oeffne Telegram, suche deinen Bot und schicke ihm /start"
}
if ($services -contains "api") {
    Write-Info "-> API-Doku im Browser: http://localhost:8000/docs"
}
Write-Info "-> Logs ansehen:   docker compose logs -f"
Write-Info "-> Alles stoppen:  docker compose down"
Write-Host ""
Write-Warn "Hinweis: Keine Finanz-/Wettberatung. Nur Recherche-Signal, keine Garantie."
