"""Central paths and settings, loaded from environment variables.

Load config/.env (if present) before reading os.environ, so a local
override file works without any extra setup by the caller.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_MATCHES_DIR = RAW_DIR / "matches"
RAW_ODDS_DIR = RAW_DIR / "odds"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = DATA_DIR / "reports"
MODELS_DIR = REPO_ROOT / "models"

for _d in (RAW_MATCHES_DIR, RAW_ODDS_DIR, PROCESSED_DIR, REPORTS_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(REPO_ROOT / "config" / ".env")

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "").strip()
TOURS = [t.strip().lower() for t in os.environ.get("TOURS", "atp,wta").split(",") if t.strip()]
START_SEASON = int(os.environ.get("START_SEASON", "2010"))

# tennis-data.co.uk hosts one xlsx per season per tour, with match results
# (surface, round, rank, date) AND odds from multiple bookmakers -- including
# Pinnacle, our closing-line benchmark -- combined in a single row per match.
# This is the sole data source: it needs no cross-source player-name matching,
# unlike combining a separate results feed with a separate odds feed.
# ATP coverage starts 2000, WTA coverage starts 2007.
ODDS_HISTORY_BASE_URL = {
    "atp": "http://www.tennis-data.co.uk/{year}/{year}.xlsx",
    "wta": "http://www.tennis-data.co.uk/{year}w/{year}.xlsx",
}
ODDS_HISTORY_FIRST_SEASON = {"atp": 2000, "wta": 2007}
