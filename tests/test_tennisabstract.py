import datetime as dt
from pathlib import Path

import pandas as pd
import requests

from tennissharp.data import tennisabstract
from tennissharp.data.tennisabstract import (
    _fetch_surface_speed_year_cached, filter_by_tour, parse_elo_html, parse_surface_speed_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_elo_html_ranks_are_numeric_and_ordered():
    html = (FIXTURES / "atp_elo_ratings_sample.html").read_text(encoding="utf-8")
    df = parse_elo_html(html, "atp")
    assert len(df) > 100
    assert df["elo_rank"].dtype.kind in "if"  # int or float, never string
    # The table is already rank-ordered in the source page.
    ranks = df["elo_rank"].tolist()
    assert ranks == sorted(ranks)
    assert df.iloc[0]["player"] == "Jannik Sinner"
    assert df.iloc[0]["elo_rank"] == 1


def test_parse_elo_html_surface_columns_present():
    html = (FIXTURES / "atp_elo_ratings_sample.html").read_text(encoding="utf-8")
    df = parse_elo_html(html, "atp")
    for col in ("elo", "helo", "celo", "gelo", "peak_elo"):
        assert col in df.columns
        assert df[col].notna().any()


def test_parse_surface_speed_html():
    html = (FIXTURES / "atp_surface_speed_sample.html").read_text(encoding="utf-8")
    df = parse_surface_speed_html(html)
    assert len(df) > 10
    assert {"date", "tournament", "surface", "ace_pct", "surface_speed"} <= set(df.columns)
    # Ace% is stored as a 0-1 fraction, not a "16.5%" string.
    assert df["ace_pct"].between(0, 1).all()
    assert df["surface_speed"].dtype.kind == "f"


def _mixed_tour_elo() -> pd.DataFrame:
    return pd.DataFrame({
        "elo_rank": [1, 2, 1, 2],
        "player": ["A", "B", "C", "D"],
        "age": [25, 26, 24, 23],
        "elo": [2200.0, 2100.0, 2050.0, 1950.0],
        "helo": [2150.0, 2050.0, 2000.0, 1900.0],
        "celo": [2100.0, 2000.0, 1950.0, 1850.0],
        "gelo": [2050.0, 1950.0, 1900.0, 1800.0],
        "peak_elo": [2250.0, 2150.0, 2100.0, 2000.0],
        "peak_month": ["2026-01", "2025-12", "2026-02", "2025-11"],
        "official_rank": [1, 2, 1, 2],
        "log_diff": [0.0, 0.1, -0.1, 0.2],
        "tour": ["atp", "atp", "wta", "wta"],
    })


def test_filter_by_tour_keeps_every_column():
    df = filter_by_tour(_mixed_tour_elo(), tour="wta")
    # Nothing dropped -- overall elo AND the hElo/cElo/gElo surface splits.
    for col in ("elo", "helo", "celo", "gelo", "peak_elo", "peak_month",
                "official_rank", "log_diff"):
        assert col in df.columns


def test_filter_by_tour_only_keeps_that_tour():
    df = filter_by_tour(_mixed_tour_elo(), tour="wta")
    assert set(df["player"]) == {"C", "D"}
    assert (df["tour"] == "wta").all()


def test_filter_by_tour_sorted_by_elo_rank():
    df = filter_by_tour(_mixed_tour_elo(), tour="wta")
    assert df.iloc[0]["player"] == "C"  # elo_rank 1
    assert df.iloc[1]["player"] == "D"  # elo_rank 2


_SPEED_HTML = (FIXTURES / "atp_surface_speed_sample.html").read_text(encoding="utf-8")


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


def test_fetch_surface_speed_year_cached_closed_season_skips_network(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(tennisabstract.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse(_SPEED_HTML))

    df1 = _fetch_surface_speed_year_cached(2020, tmp_path)
    assert len(calls) == 1
    assert not df1.empty
    assert (tmp_path / "atp_surface_speed_2020.html").exists()

    df2 = _fetch_surface_speed_year_cached(2020, tmp_path)  # closed season, cached
    assert len(calls) == 1  # no second network call
    pd.testing.assert_frame_equal(df1, df2)


def test_fetch_surface_speed_year_cached_always_refetches_current_season(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(tennisabstract.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse(_SPEED_HTML))
    current_year = dt.date.today().year

    _fetch_surface_speed_year_cached(current_year, tmp_path)
    _fetch_surface_speed_year_cached(current_year, tmp_path)
    assert len(calls) == 2  # cache file exists but is ignored for the in-progress season


def test_fetch_surface_speed_year_cached_falls_back_to_cache_on_failure(tmp_path, monkeypatch):
    # First call succeeds and populates the cache.
    monkeypatch.setattr(tennisabstract.requests, "get", lambda *a, **k: _FakeResponse(_SPEED_HTML))
    good = _fetch_surface_speed_year_cached(2020, tmp_path)

    # A later re-fetch (force=True) that fails should fall back to the cache
    # instead of dropping that year's data entirely.
    monkeypatch.setattr(tennisabstract.requests, "get", lambda *a, **k: (_ for _ in ()).throw(
        requests.ConnectionError("network down")))
    recovered = _fetch_surface_speed_year_cached(2020, tmp_path, force=True)
    pd.testing.assert_frame_equal(good, recovered)


def test_fetch_surface_speed_year_cached_missing_cache_on_failure_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(tennisabstract.requests, "get", lambda *a, **k: (_ for _ in ()).throw(
        requests.ConnectionError("network down")))
    df = _fetch_surface_speed_year_cached(2020, tmp_path)
    assert df.empty
