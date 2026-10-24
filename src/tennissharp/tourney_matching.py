"""Join Tennis Abstract's per-tournament-edition surface-speed ratings onto
tennis-data.co.uk match rows by (season, tournament name).

Unlike Tennis Abstract's Elo ratings (a live snapshot, safe only for scoring
*current* matchups -- see data/tennisabstract.py's module docstring), the
year-by-year surface-speed report gives one dated rating per tournament
*edition*, so it reflects only information available at the time that
edition was played. That makes it safe to join into historical training
data without lookahead bias.

Tournament names differ slightly between sources (e.g. "Australian Open" vs.
tennis-data.co.uk's occasional "Australian Open 2"), so we match on a
normalized name within the same season rather than an exact string.
"""
from __future__ import annotations

import re

import pandas as pd

_DROP_WORDS = re.compile(
    r"\b(atp|wta|masters|international|open|cup|championships|presented|by|series|tour|finals?)\b"
)


def normalize_tourney_name(name: str) -> str:
    name = str(name).lower()
    name = _DROP_WORDS.sub(" ", name)
    name = re.sub(r"\d+", " ", name)
    name = re.sub(r"[^a-z\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def build_surface_speed_index(speed_df: pd.DataFrame) -> dict[tuple[int, str], float]:
    index: dict[tuple[int, str], float] = {}
    for row in speed_df.itertuples(index=False):
        season = row.date.year
        key = (season, normalize_tourney_name(row.tournament))
        # A tournament can appear more than once if it moved surfaces/dates
        # across two report pulls; keep the most recent value seen.
        index[key] = row.surface_speed
    return index


def load_surface_speed_index(cache_path: "os.PathLike | str", start_season: int,
                              force: bool = False) -> dict:
    """Load the cached Tennis Abstract surface-speed history CSV if present,
    otherwise fetch it fresh (and write the cache for next time).
    """
    import os

    from tennissharp.data import tennisabstract

    if not force and os.path.exists(cache_path):
        speed_df = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        speed_df = tennisabstract.fetch_surface_speed_history(start_season)
        speed_df.to_csv(cache_path, index=False)
    return build_surface_speed_index(speed_df)


def lookup_surface_speed(index: dict[tuple[int, str], float], season: int, tournament: str,
                          default: float = 1.0) -> float:
    key = (season, normalize_tourney_name(tournament))
    if key in index:
        return index[key]
    # Fall back to a substring match within the same season -- handles minor
    # naming drift ("Australian Open" vs "Australian Open Qualifying", etc.)
    normalized = key[1]
    if not normalized:
        return default
    for (idx_season, idx_name), speed in index.items():
        if idx_season == season and (normalized in idx_name or idx_name in normalized):
            return speed
    return default
