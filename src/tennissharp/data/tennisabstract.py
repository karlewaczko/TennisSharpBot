"""Tennis Abstract (Jeff Sackmann's site) Elo ratings + surface speed ratings.

These are the "official"/reference Elo ratings the wider tennis-analytics
community treats as authoritative -- more sophisticated than our own
from-scratch Elo (they fold in ITF/Challenger results, peak ratings, etc.)
-- so we ingest them directly as extra features rather than trying to
replicate them.

Both pages are plain server-rendered HTML tables (`pandas.read_html` handles
them directly), unlike tennisabstract.com/cgi-bin/leaders.cgi, whose stat
leaderboards are built client-side from a large, undocumented internal JS
array and are deliberately NOT scraped here -- see README for why.
"""
from __future__ import annotations

import io
import re

import pandas as pd
import requests

ELO_URLS = {
    "atp": "https://tennisabstract.com/reports/atp_elo_ratings.html",
    "wta": "https://tennisabstract.com/reports/wta_elo_ratings.html",
}
# Ace-rate is far noisier on the WTA tour (fewer aces), so Tennis Abstract
# only publishes surface-speed ratings for the ATP; we apply them to shared
# venues on the WTA side too, on the (usual) assumption the court plays the
# same regardless of tour.
SURFACE_SPEED_ROLLING_URL = "https://tennisabstract.com/reports/atp_surface_speed.html"
SURFACE_SPEED_YEAR_URL = "https://www.tennisabstract.com/cgi-bin/surface-speed.cgi?year={year}"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)"}

_ELO_COLUMN_MAP = {
    "Elo Rank": "elo_rank",
    "Player": "player",
    "Age": "age",
    "Elo": "elo",
    "hElo Rank": "helo_rank",
    "hElo": "helo",
    "cElo Rank": "celo_rank",
    "cElo": "celo",
    "gElo Rank": "gelo_rank",
    "gElo": "gelo",
    "Peak Elo": "peak_elo",
    "Peak Month": "peak_month",
    "ATP Rank": "official_rank",
    "WTA Rank": "official_rank",
    "Log diff": "log_diff",
}


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df.rename(columns=_ELO_COLUMN_MAP)


_ELO_NUMERIC_COLUMNS = [
    "elo_rank", "age", "elo", "helo_rank", "helo", "celo_rank", "celo",
    "gelo_rank", "gelo", "peak_elo", "official_rank", "log_diff",
]


def parse_elo_html(html: str, tour: str) -> pd.DataFrame:
    tables = pd.read_html(io.StringIO(html))
    # The ratings table is the largest one on the page (the intro blurb is
    # its own single-cell table); id="reportable" isn't preserved by read_html
    # so we pick by shape instead.
    data = max(tables, key=lambda t: t.shape[0] * t.shape[1])
    data = _clean_columns(data)
    data["tour"] = tour
    # read_html's dtype inference is inconsistent (e.g. "Elo Rank" comes back
    # as strings whenever any row breaks the numeric pattern), so coerce
    # explicitly rather than trust it -- an un-coerced rank column sorts
    # lexicographically (1, 10, 100, 11, ...) instead of numerically.
    for col in _ELO_NUMERIC_COLUMNS:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
    # Player names render with &nbsp; between first/last name in the source
    # HTML, which read_html preserves as literal U+00A0 -- normalize to a
    # regular space or every downstream name match silently fails.
    data["player"] = data["player"].astype(str).str.replace("\xa0", " ", regex=False)
    return data.dropna(subset=["player"]).reset_index(drop=True)


def fetch_elo_ratings(tour: str) -> pd.DataFrame:
    resp = requests.get(ELO_URLS[tour], headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_elo_html(resp.text, tour)


def fetch_all_elo_ratings() -> pd.DataFrame:
    return pd.concat([fetch_elo_ratings("atp"), fetch_elo_ratings("wta")], ignore_index=True)


def filter_by_tour(df: pd.DataFrame, tour: str) -> pd.DataFrame:
    """One tour's Elo ratings, every column kept -- overall `elo` plus the
    surface splits `helo`/`celo`/`gelo` (and their own ranks). Just a filter,
    e.g. `tour="wta"` for a standalone WTA file with the same schema as
    `fetch_all_elo_ratings()`'s combined ATP+WTA table.
    """
    out = df[df["tour"] == tour].copy()
    return out.sort_values("elo_rank").reset_index(drop=True)


_SPEED_COLUMN_MAP = {
    "Date": "date",
    "Tournament": "tournament",
    "Surface": "surface",
    "Ace%": "ace_pct",
    "Surface Speed": "surface_speed",
}


def parse_surface_speed_html(html: str) -> pd.DataFrame:
    tables = pd.read_html(io.StringIO(html))
    data = max(tables, key=lambda t: t.shape[0] * t.shape[1])
    data = _clean_columns(data)
    data = data.rename(columns=_SPEED_COLUMN_MAP)
    data["tournament"] = data["tournament"].astype(str).str.replace("\xa0", " ", regex=False)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["ace_pct"] = pd.to_numeric(data["ace_pct"].astype(str).str.rstrip("%"), errors="coerce") / 100.0
    data["surface_speed"] = pd.to_numeric(data["surface_speed"], errors="coerce")
    return data.dropna(subset=["date", "tournament"]).reset_index(drop=True)


def fetch_surface_speed(year: int | None = None) -> pd.DataFrame:
    """`year=None` gets the rolling last-52-weeks view; a specific year hits
    the archived per-season report (available back to 1991)."""
    url = SURFACE_SPEED_ROLLING_URL if year is None else SURFACE_SPEED_YEAR_URL.format(year=year)
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_surface_speed_html(resp.text)


def fetch_surface_speed_history(start_year: int, end_year: int | None = None) -> pd.DataFrame:
    import datetime as dt
    end_year = end_year or dt.date.today().year
    frames = [fetch_surface_speed(year) for year in range(start_year, end_year + 1)]
    frames = [f for f in frames if not f.empty]
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined.drop_duplicates(subset=["date", "tournament"]).sort_values("date").reset_index(drop=True)
