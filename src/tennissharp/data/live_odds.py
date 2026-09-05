"""Live tennis odds via The Odds API (https://the-odds-api.com).

Requires the user's own ODDS_API_KEY (config.py / config/.env). We don't
scrape bookmaker sites directly -- that's both a Terms-of-Service and, for
some German-licensed operators, a legal grey area. The Odds API is a
legitimate third-party aggregator with its own ToS and a free tier.

Only used by scripts/find_value_bets.py; all historical backtesting works
without any API key.
"""
from __future__ import annotations

import requests

from tennissharp import config

BASE_URL = "https://api.the-odds-api.com/v4"


def _require_key() -> str:
    if not config.ODDS_API_KEY:
        raise RuntimeError(
            "ODDS_API_KEY is not set. Get a free key at https://the-odds-api.com "
            "and put it in config/.env (see config/settings.example.env)."
        )
    return config.ODDS_API_KEY


def list_active_tennis_sports() -> list[dict]:
    """Tennis sport keys change with the tour calendar (e.g. one key per
    active Slam/tour event), so we discover them instead of hardcoding.
    """
    resp = requests.get(f"{BASE_URL}/sports", params={"apiKey": _require_key()}, timeout=20)
    resp.raise_for_status()
    return [s for s in resp.json() if s.get("group", "").lower() == "tennis" and s.get("active")]


def get_odds(sport_key: str, regions: str = "eu", markets: str = "h2h") -> list[dict]:
    resp = requests.get(
        f"{BASE_URL}/sports/{sport_key}/odds",
        params={"apiKey": _require_key(), "regions": regions, "markets": markets, "oddsFormat": "decimal"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_all_active_tennis_odds(regions: str = "eu") -> list[dict]:
    events = []
    for sport in list_active_tennis_sports():
        events.extend(get_odds(sport["key"], regions=regions))
    return events
