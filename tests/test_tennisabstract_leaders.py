import pandas as pd
import pytest

from tennissharp.data import tennisabstract_leaders as L


def _match_row(**overrides) -> list:
    """One MATCH_COLUMNS-shaped row, defaults chosen so every field an
    aggregation formula reads is a small round number -- overrides fill in
    the specific match under test."""
    base = {
        "date": 20260101, "tourn": "Test Event", "surf": "Hard", "level": "A",
        "wl": "W", "player": "A", "rank": 10, "seed": "", "entry": "", "round": "R32",
        "score": "6-4 6-3", "max": 3, "opp": "B", "orank": 50, "oseed": "", "oentry": "",
        "ohand": "R", "obh": 2, "obday": 19950101, "oht": 185, "ocountry": "XXX", "oactive": "",
        "tbw": 0, "tbl": 0, "setw": 2, "setl": 0,
        "time": 90, "aces": 5, "dfs": 2, "pts": 70, "firsts": 40, "fwon": 30, "swon": 15,
        "games": 10, "saved": 3, "chances": 4,
        "oaces": 3, "odfs": 1, "opts": 65, "ofirsts": 35, "ofwon": 20, "oswon": 10,
        "ogames": 9, "osaved": 2, "ochances": 5,
    }
    base.update(overrides)
    return [base[col] for col in L.MATCH_COLUMNS]


def _matches_df(rows: list[list]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=L.MATCH_COLUMNS)
    df["date"] = pd.to_numeric(df["date"])
    for col in L._SUM_COLUMNS:
        df[col] = pd.to_numeric(df[col])
    return df


# Two matches for player A, hand-computed expected serve/return stats in the
# module docstring-adjacent comment above each assertion below.
_TWO_MATCHES = _matches_df([
    _match_row(surf="Hard", wl="W", orank=50),
    _match_row(surf="Clay", wl="L", score="3-6 4-6", orank=30,
               aces=2, dfs=4, pts=60, firsts=32, fwon=18, swon=10, games=8, saved=2, chances=5,
               oaces=4, odfs=0, opts=55, ofirsts=30, ofwon=22, oswon=12, ogames=8, osaved=1, ochances=4),
])


def test_parse_matchmx_valid_json():
    js = 'var ychoices=["x"];\nvar matchmx = [["a","b"],["c","d"]];\n'
    assert L._parse_matchmx(js) == [["a", "b"], ["c", "d"]]


def test_normalize_row_length_truncates_and_pads():
    long_row = list(range(65))
    assert L._normalize_row_length(long_row) == list(range(len(L.MATCH_COLUMNS)))
    short_row = [1, 2, 3]
    normalized = L._normalize_row_length(short_row)
    assert len(normalized) == len(L.MATCH_COLUMNS)
    assert normalized[:3] == [1, 2, 3]


def test_compute_serve_leaders_matches_hand_calculation():
    out = L.compute_serve_leaders(_TWO_MATCHES)
    row = out[out["player"] == "A"].iloc[0]
    assert row["matches"] == 2
    assert row["wins"] == 1 and row["losses"] == 1
    assert row["aces"] == 7 and row["dfs"] == 6
    assert row["spw"] == pytest.approx(73 / 130)
    assert row["ace_pct"] == pytest.approx(7 / 130)
    assert row["hold_pct"] == pytest.approx(14 / 18)
    assert row["pts_per_service_game"] == pytest.approx(130 / 18)


def test_compute_return_leaders_matches_hand_calculation():
    out = L.compute_return_leaders(_TWO_MATCHES)
    row = out[out["player"] == "A"].iloc[0]
    assert row["rpw"] == pytest.approx(1 - 64 / 120)
    assert row["vs_ace_pct"] == pytest.approx(7 / 120)
    assert row["break_pct"] == pytest.approx(6 / 17)
    assert row["median_opp_rank"] == pytest.approx(40)
    assert row["mean_opp_rank"] == pytest.approx(40)


def test_filter_surface_keeps_only_matching_rows():
    hard_only = L._filter_surface(_TWO_MATCHES, "Hard")
    assert set(hard_only["surf"]) == {"Hard"}
    assert len(L._filter_surface(_TWO_MATCHES, "All")) == len(_TWO_MATCHES)


def test_leaders_for_surface_filters_before_aggregating():
    hard_serve = L.leaders_for(_TWO_MATCHES, "serve", "Hard")
    row = hard_serve[hard_serve["player"] == "A"].iloc[0]
    assert row["matches"] == 1
    assert row["aces"] == 5  # only the Hard-court match's aces


def test_last_52_weeks_filter_excludes_older_matches():
    df = _matches_df([
        _match_row(date=20260601),  # within a year of "today"
        _match_row(date=20200101),  # long expired
    ])
    filtered = L._filter_last_52_weeks(df, as_of=20260801)
    assert len(filtered) == 1
    assert filtered.iloc[0]["date"] == 20260601


def test_retired_walkover_matches_excluded_from_win_loss_but_not_stat_sums():
    df = _matches_df([
        _match_row(wl="W", score="6-4 6-3"),
        _match_row(wl="W", score="RET", aces=1, dfs=0, pts=10, firsts=5, fwon=5, swon=2,
                   games=2, saved=0, chances=0, oaces=0, odfs=0, opts=8, ofirsts=4, ofwon=2,
                   oswon=1, ogames=1, osaved=0, ochances=0),
    ])
    out = L.compute_serve_leaders(df)
    row = out[out["player"] == "A"].iloc[0]
    assert row["matches"] == 1  # RET match doesn't count as a decided match
    assert row["aces"] == 6  # but its raw stats still get summed in (matches TA's own JS)
