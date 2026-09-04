"""stats.tennismylife.org: match results WITH per-match serve statistics.

Why a second results source when tennis-data.co.uk already provides one:
the two carry different things and neither is a superset.

    tennis-data.co.uk   results + bookmaker odds, ATP/WTA main tour only,
                        no match statistics at all
    TennisMyLife        results + serve/return counts, and additionally
                        Challenger, ATP qualifying and a wider WTA field,
                        no odds

Measured on 2026: 3971 matches and 556 players in our existing feed
against 10439 and 1263 here, with serve counts present on 99.3% of rows.
That coverage gap is exactly what `LiveState.is_stale` was built to flag
-- Smith has one match in the old feed since March and 84 here, through
28.08. So this source supplies the history and the features, and
tennis-data.co.uk stays the source of prices.

The schema is Jeff Sackmann's, which is the de-facto standard: one row
per match, `w_`/`l_` prefixed serve columns for winner and loser.
"""
from __future__ import annotations

import logging
import re

import pandas as pd
import requests

from tennissharp import config
from tennissharp.data.odds_history import _fetch_season_file

logger = logging.getLogger(__name__)

BASE_URL = "https://stats.tennismylife.org"
INDEX_URL = f"{BASE_URL}/api/data-files"

# One file per tour and season. `atp` is main tour only, so the other three
# are what actually widens the pool.
FILE_PATTERNS = {
    "atp": "{year}.csv",
    "challenger": "{year}_challenger.csv",
    "wta": "{year}_wta.csv",
    "atp_quali": "atp_quali/{year}_atp_quali.csv",
}

SERVE_COLUMNS = ("ace", "df", "svpt", "1stIn", "1stWon", "2ndWon",
                 "SvGms", "bpSaved", "bpFaced")


def _local_name(pattern_key: str, year: int) -> str:
    return FILE_PATTERNS[pattern_key].format(year=year).replace("/", "_")


def download_season(pattern_key: str, year: int, force: bool = False):
    """Cache one season file locally; returns the path or None."""
    dest = config.RAW_DIR / "tennismylife" / _local_name(pattern_key, year)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size and not force:
        return dest
    url = f"{BASE_URL}/data/{FILE_PATTERNS[pattern_key].format(year=year)}"
    try:
        dest.write_bytes(_fetch_season_file(url))
    except requests.RequestException as exc:
        logger.warning("No TennisMyLife data for %s %s (%s)", pattern_key, year, exc)
        return None
    return dest


def parse_season(path) -> pd.DataFrame:
    """One season file, normalised onto this repo's column names."""
    raw = pd.read_csv(path, low_memory=False)
    if raw.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(raw["tourney_date"], format="%Y%m%d", errors="coerce"),
        "tournament": raw.get("tourney_name"),
        "surface": raw.get("surface"),
        "round": raw.get("round"),
        "best_of": pd.to_numeric(raw.get("best_of"), errors="coerce"),
        "winner": raw.get("winner_name"),
        "loser": raw.get("loser_name"),
        "winner_rank": pd.to_numeric(raw.get("winner_rank"), errors="coerce"),
        "loser_rank": pd.to_numeric(raw.get("loser_rank"), errors="coerce"),
        "winner_pts": pd.to_numeric(raw.get("winner_rank_points"), errors="coerce"),
        "loser_pts": pd.to_numeric(raw.get("loser_rank_points"), errors="coerce"),
        "tier": raw.get("tourney_level"),
        # Present here and absent from tennis-data.co.uk entirely.
        "indoor": raw.get("indoor").eq("I") if "indoor" in raw else False,
        "draw_size": pd.to_numeric(raw.get("draw_size"), errors="coerce"),
        "minutes": pd.to_numeric(raw.get("minutes"), errors="coerce"),
    })
    for side in ("w", "l"):
        for col in SERVE_COLUMNS:
            src = f"{side}_{col}"
            out[f"{'winner' if side == 'w' else 'loser'}_{col.lower()}"] = (
                pd.to_numeric(raw.get(src), errors="coerce"))
    return out.dropna(subset=["date", "winner", "loser"])


def load_all(start_season: int | None = None, tours=None) -> pd.DataFrame:
    """Every cached season across the requested tours, oldest first."""
    start = start_season or config.START_SEASON
    end = pd.Timestamp.now().year
    keys = list(tours or FILE_PATTERNS)
    frames = []
    for key in keys:
        for year in range(start, end + 1):
            path = download_season(key, year)
            if path is None:
                continue
            df = parse_season(path)
            if df.empty:
                continue
            df["source_tour"] = key
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values("date", kind="stable").reset_index(drop=True)
    out["match_id"] = [
        f"tml_{d:%Y%m%d}_{_slug(w)}_{_slug(l)}"
        for d, w, l in zip(out["date"], out["winner"], out["loser"])
    ]
    return out


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())[:16]


def serve_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Per-match serve-point win rate for each side.

    This is the quantity every point-based tennis model is built on
    (Klaassen & Magnus): the share of points a player wins behind his own
    serve. Our existing features never had it -- tennis-data.co.uk carries
    no statistics at all -- so the model has been working from results
    alone.
    """
    out = df.copy()
    for who in ("winner", "loser"):
        svpt = out[f"{who}_svpt"]
        won = out[f"{who}_1stwon"] + out[f"{who}_2ndwon"]
        # A serve line of zero points is a walkover or a missing row.
        out[f"{who}_serve_win_rate"] = (won / svpt).where(svpt > 0)
        out[f"{who}_ace_rate"] = (out[f"{who}_ace"] / svpt).where(svpt > 0)
        out[f"{who}_df_rate"] = (out[f"{who}_df"] / svpt).where(svpt > 0)
    # Return points won is the mirror of the opponent's serve.
    out["winner_return_win_rate"] = 1 - out["loser_serve_win_rate"]
    out["loser_return_win_rate"] = 1 - out["winner_serve_win_rate"]
    return out


def last_seen_index(start_season: int | None = None) -> dict:
    """{player name -> date of their most recent match in this source}.

    Used to answer the question `LiveState.is_stale` actually cares about:
    has this player been playing lately? Our own Elo can only answer from
    tennis-data.co.uk, which carries no challengers and no qualifying, so
    it says "no" for anyone whose recent tennis happened there. Smith had
    one match in that feed since March and 84 here through 28.08.
    """
    matches = load_all(start_season=start_season)
    if matches.empty:
        return {}
    seen = {}
    for col in ("winner", "loser"):
        latest = matches.groupby(col)["date"].max()
        for player, when in latest.items():
            if player not in seen or when > seen[player]:
                seen[player] = when
    return seen
