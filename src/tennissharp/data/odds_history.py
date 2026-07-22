"""Download and normalize historical match+odds data from tennis-data.co.uk.

Each season/tour file is a single spreadsheet with one row per match holding
both the result (surface, round, rank, score) and odds from several
bookmakers (Pinnacle, bet365, market max/average). Using one combined source
avoids having to fuzzy-match player names across a separate results feed and
a separate odds feed.
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd
import requests

from tennissharp import config

logger = logging.getLogger(__name__)

# Column names vary slightly by season (bookmakers come and go), but these
# are present in effectively every file since each tour's first season.
CORE_COLUMNS = [
    "Date", "Tournament", "Location", "Surface", "Round", "Best of",
    "Winner", "Loser", "WRank", "LRank", "WPts", "LPts",
]
ODDS_COLUMN_PAIRS = {
    "pinnacle": ("PSW", "PSL"),
    "bet365": ("B365W", "B365L"),
    "market_max": ("MaxW", "MaxL"),
    "market_avg": ("AvgW", "AvgL"),
}


def _download_season(tour: str, year: int, force: bool = False) -> pd.DataFrame | None:
    url = config.ODDS_HISTORY_BASE_URL[tour].format(year=year)
    dest = config.RAW_ODDS_DIR / f"{tour}_{year}.xlsx"
    is_current_season = year >= dt.date.today().year
    if dest.exists() and not force and not is_current_season:
        return pd.read_excel(dest)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        if dest.exists():
            logger.warning("Download failed for %s %s (%s); using cached copy", tour, year, exc)
            return pd.read_excel(dest)
        logger.warning("No data for %s %s (%s)", tour, year, exc)
        return None
    dest.write_bytes(resp.content)
    return pd.read_excel(dest)


def fetch_tour(tour: str, start_season: int | None = None, force: bool = False) -> pd.DataFrame:
    """Download (or load cached) season files for one tour and concatenate them."""
    first = config.ODDS_HISTORY_FIRST_SEASON[tour]
    start = max(start_season or config.START_SEASON, first)
    end = dt.date.today().year
    frames = []
    for year in range(start, end + 1):
        df = _download_season(tour, year, force=force)
        if df is None or df.empty:
            continue
        df = df.copy()
        df["season"] = year
        df["tour"] = tour
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Tidy raw tennis-data.co.uk rows into a stable schema used downstream."""
    if df.empty:
        return df
    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df["Date"], errors="coerce")
    out["tour"] = df["tour"]
    out["season"] = df["season"]
    out["tournament"] = df["Tournament"]
    out["location"] = df["Location"]
    out["surface"] = df["Surface"].fillna("Unknown")
    out["round"] = df["Round"]
    out["best_of"] = pd.to_numeric(df["Best of"], errors="coerce")
    # tournament tier lives under different column names per tour
    out["tier"] = df["Series"] if "Series" in df.columns else df.get("Tier")
    out["winner"] = df["Winner"].astype(str).str.strip()
    out["loser"] = df["Loser"].astype(str).str.strip()
    out["winner_rank"] = pd.to_numeric(df["WRank"], errors="coerce")
    out["loser_rank"] = pd.to_numeric(df["LRank"], errors="coerce")
    out["winner_pts"] = pd.to_numeric(df.get("WPts"), errors="coerce")
    out["loser_pts"] = pd.to_numeric(df.get("LPts"), errors="coerce")
    for label, (wcol, lcol) in ODDS_COLUMN_PAIRS.items():
        w_odds = pd.to_numeric(df.get(wcol), errors="coerce")
        l_odds = pd.to_numeric(df.get(lcol), errors="coerce")
        # A handful of rows carry 0 or sub-1.0 placeholder odds (walkovers,
        # data entry gaps) instead of a blank cell -- decimal odds below 1.0
        # are not valid prices, so treat them as missing.
        out[f"{label}_w"] = w_odds.where(w_odds > 1.0)
        out[f"{label}_l"] = l_odds.where(l_odds > 1.0)
    out = out.dropna(subset=["date", "winner", "loser"])
    # A handful of rows carry data-entry typos in the year (e.g. a 2029 date
    # in an otherwise-2026 season file); drop anything past today.
    out = out[out["date"] <= pd.Timestamp.now().normalize()]
    out = out.sort_values("date").reset_index(drop=True)
    out["match_id"] = out.index.astype(str) + "_" + out["tour"]
    return out


def load_all(tours: list[str] | None = None, start_season: int | None = None,
             force: bool = False) -> pd.DataFrame:
    """Fetch, normalize and combine ATP + WTA history into one dataframe."""
    tours = tours or config.TOURS
    frames = [normalize(fetch_tour(tour, start_season=start_season, force=force)) for tour in tours]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return combined.sort_values("date").reset_index(drop=True)
