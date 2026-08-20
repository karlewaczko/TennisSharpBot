"""Shared data-access layer for the Telegram bot and the REST API.

Both front ends read the same processed CSVs that `scripts/update_data.py`
refreshes, so this module is the single place that knows those file paths
and schemas -- neither front end should read a CSV directly.

Everything here is read-only and returns plain pandas DataFrames / dicts;
formatting for a specific channel (Telegram text, JSON) lives in
`bot/formatting.py` and `api.py` respectively.
"""
from __future__ import annotations

import pandas as pd

from tennissharp import config


class DataNotReadyError(RuntimeError):
    """Raised when a processed file is missing -- i.e. scripts/update_data.py
    hasn't been run yet. Both front ends should turn this into a friendly
    "still warming up" message rather than a stack trace.
    """


def _require(path, what: str) -> None:
    if not path.exists():
        raise DataNotReadyError(f"{what} not found at {path} -- run scripts/update_data.py first.")


def get_rankings(tour: str = "atp", top_n: int = 10, source: str = "ta") -> pd.DataFrame:
    """`source='ta'` (default) uses Tennis Abstract's tour-tagged Elo ratings.
    `source='own'` uses our own homegrown Elo snapshot, which doesn't track
    which tour each player belongs to, so `tour` is ignored for it.
    """
    if source == "own":
        path = config.PROCESSED_DIR / "elo_ratings_current.csv"
        _require(path, "Own Elo ratings")
        df = pd.read_csv(path)
        return df[df["matches_played"] >= 10].sort_values("elo_overall", ascending=False).head(top_n)

    path = config.PROCESSED_DIR / "ta_elo_current.csv"
    _require(path, "Tennis Abstract Elo ratings")
    df = pd.read_csv(path)
    return df[df["tour"] == tour.lower()].sort_values("elo_rank").head(top_n)


def get_wta_general_rankings(top_n: int = 10) -> pd.DataFrame:
    """WTA Elo ratings without the surface-specific hElo/cElo/gElo columns --
    just the overall rating, age, peak, and official-rank comparison. See
    `tennisabstract.general_elo_only`.
    """
    path = config.PROCESSED_DIR / "ta_elo_wta_general.csv"
    _require(path, "WTA general Elo ratings")
    df = pd.read_csv(path)
    return df.sort_values("elo_rank").head(top_n)


def get_surface_speed(tournament: str | None = None, top_n: int = 10) -> pd.DataFrame:
    """Without `tournament`, returns the fastest `top_n` tournaments from the
    most recent season on record. With it, returns that tournament's rating
    history (most recent editions first).
    """
    path = config.PROCESSED_DIR / "ta_surface_speed_history.csv"
    _require(path, "Surface speed ratings")
    df = pd.read_csv(path, parse_dates=["date"])

    if tournament:
        from tennissharp.tourney_matching import normalize_tourney_name
        key = normalize_tourney_name(tournament)
        matches = df[df["tournament"].apply(lambda t: normalize_tourney_name(t) == key)]
        return matches.sort_values("date", ascending=False).head(top_n)

    latest_season = df["date"].dt.year.max()
    return df[df["date"].dt.year == latest_season].sort_values("surface_speed", ascending=False).head(top_n)


def get_upcoming_matches(tour: str | None = None, limit: int = 20) -> pd.DataFrame:
    path = config.PROCESSED_DIR / "tennisexplorer_upcoming.csv"
    _require(path, "Upcoming matches")
    df = pd.read_csv(path)
    if tour:
        # tennisexplorer_upcoming.csv doesn't tag tour explicitly; filter by
        # the "-men/"/"-women/" suffix TennisExplorer puts on tournament URLs.
        suffix = "-men/" if tour.lower() == "atp" else "-women/"
        df = df[df["tournament_url"].str.contains(suffix, regex=False, na=False)]
    return df.head(limit)


def find_player_slug(name_query: str) -> tuple[str, str] | None:
    """Best-effort: look up a player's TennisExplorer slug from today/
    tomorrow's schedule cache. Returns (display_name, slug) or None.
    Only players currently listed in the cached schedule are resolvable --
    good enough for "who's playing today", not a general player database.
    """
    path = config.PROCESSED_DIR / "tennisexplorer_upcoming.csv"
    _require(path, "Upcoming matches")
    df = pd.read_csv(path)
    query = name_query.strip().lower()
    for col_name, col_slug in (("player1", "player1_slug"), ("player2", "player2_slug")):
        hit = df[df[col_name].str.lower().str.contains(query, regex=False, na=False)]
        if not hit.empty:
            row = hit.iloc[0]
            return row[col_name], row[col_slug]
    return None


def get_head_to_head(player1_query: str, player2_query: str) -> dict:
    from tennissharp.data.tennisexplorer import fetch_head_to_head, head_to_head_summary

    p1 = find_player_slug(player1_query)
    p2 = find_player_slug(player2_query)
    if not p1 or not p2:
        missing = player1_query if not p1 else player2_query
        raise ValueError(f"Couldn't find '{missing}' in today/tomorrow's schedule -- "
                          "head-to-head lookup only works for players currently listed there.")
    (name1, slug1), (name2, slug2) = p1, p2
    history = fetch_head_to_head(slug1, slug2)
    wins1, wins2 = head_to_head_summary(history, name1, name2)
    return {"player1": name1, "player2": name2, "wins1": wins1, "wins2": wins2, "history": history}


def get_value_bets(edge_threshold: float = 0.03, kelly_fraction: float = 0.25,
                    bankroll: float = 10_000.0, regions: str = "eu") -> pd.DataFrame:
    """Live value bets via The Odds API -- requires ODDS_API_KEY. Raises
    RuntimeError (via live_odds._require_key) with a clear message if unset.
    """
    import joblib

    from tennissharp.data import live_odds
    from tennissharp.model import load as load_model
    from tennissharp.value_finder import find_value_bets

    model_path = config.MODELS_DIR / "win_probability_model.joblib"
    state_path = config.MODELS_DIR / "live_state.joblib"
    _require(model_path, "Trained model")
    _require(state_path, "Player state")

    model = load_model(model_path)
    state = joblib.load(state_path)
    ta_elo_path = config.PROCESSED_DIR / "ta_elo_current.csv"
    ta_elo = pd.read_csv(ta_elo_path) if ta_elo_path.exists() else None

    events = live_odds.fetch_all_active_tennis_odds(regions=regions)
    return find_value_bets(state, model, events, edge_threshold=edge_threshold,
                            kelly_fraction=kelly_fraction, bankroll=bankroll, ta_elo=ta_elo)
