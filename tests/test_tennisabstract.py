from pathlib import Path

import pandas as pd

from tennissharp.data.tennisabstract import (
    GENERAL_ELO_COLUMNS, general_elo_only, parse_elo_html, parse_surface_speed_html,
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


def test_general_elo_only_drops_surface_columns():
    df = general_elo_only(_mixed_tour_elo())
    assert set(df.columns) == set(GENERAL_ELO_COLUMNS)
    for col in ("helo", "celo", "gelo", "helo_rank", "celo_rank", "gelo_rank"):
        assert col not in df.columns


def test_general_elo_only_filters_by_tour():
    df = general_elo_only(_mixed_tour_elo(), tour="wta")
    assert set(df["player"]) == {"C", "D"}
    assert (df["tour"] == "wta").all()


def test_general_elo_only_reranks_by_overall_elo():
    df = general_elo_only(_mixed_tour_elo(), tour="wta")
    # C (2050) outranks D (1950) on overall elo -- confirm re-ranked 1, 2.
    assert df.iloc[0]["player"] == "C"
    assert df.iloc[0]["elo_rank"] == 1
    assert df.iloc[1]["player"] == "D"
    assert df.iloc[1]["elo_rank"] == 2
