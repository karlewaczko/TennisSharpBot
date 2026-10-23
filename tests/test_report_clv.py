"""Closing-line value from the dashboard's own logs."""
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_SCRIPTS = Path(__file__).parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location("report_clv", _SCRIPTS / "report_clv.py")


@pytest.fixture(scope="module")
def rc():
    sys.path.insert(0, str(_SCRIPTS))
    try:
        mod = importlib.util.module_from_spec(_SPEC)
        _SPEC.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(_SCRIPTS))


def _snaps():
    return pd.DataFrame([
        {"taken_at": pd.Timestamp("2026-10-22 10:00", tz="UTC"), "match_id": "7", "date": "2026-10-23",
         "start_time": "2026-10-23T15:00+00:00", "tournament": "Lyon", "player1": "Cobolli F.",
         "player2": "Nakashima B.", "venue": "Pinnacle", "kind": "book", "odds1": 2.50, "odds2": 1.55},
        {"taken_at": pd.Timestamp("2026-10-23 14:00", tz="UTC"), "match_id": "7", "date": "2026-10-23",
         "start_time": "2026-10-23T15:00+00:00", "tournament": "Lyon", "player1": "Cobolli F.",
         "player2": "Nakashima B.", "venue": "Pinnacle", "kind": "book", "odds1": 2.20, "odds2": 1.70},
        # Taken after the start: in-play, must not count as the close.
        {"taken_at": pd.Timestamp("2026-10-23 16:00", tz="UTC"), "match_id": "7", "date": "2026-10-23",
         "start_time": "2026-10-23T15:00+00:00", "tournament": "Lyon", "player1": "Cobolli F.",
         "player2": "Nakashima B.", "venue": "Pinnacle", "kind": "book", "odds1": 5.00, "odds2": 1.15},
    ])


def test_closing_pair_is_the_last_quote_before_the_start(rc):
    closes = rc.closing_pairs(_snaps())
    odds, _ = closes[("7", "Pinnacle")]
    assert odds == [2.20, 1.70]


def test_clv_is_measured_on_the_picked_side(rc):
    picks = pd.DataFrame([
        {"taken_at": "2026-10-22T10:00", "match_id": "7", "date": "2026-10-23", "tournament": "Lyon",
         "player": "Cobolli F.", "venue": "bet365", "kind": "book", "source": "value", "odds": 2.60,
         "fair_prob": 0.41, "ev": 0.066, "ref_book": "Pinnacle"},
        {"taken_at": "2026-10-22T10:00", "match_id": "7", "date": "2026-10-23", "tournament": "Lyon",
         "player": "Nakashima B.", "venue": "bet365", "kind": "book", "source": "value", "odds": 1.60,
         "fair_prob": 0.59, "ev": -0.05, "ref_book": "Pinnacle"},
    ])
    out = rc.attach_clv(picks, _snaps())
    # Cobolli closed shorter (2.50 -> 2.20): the 2.60 taken beats the close.
    assert out.iloc[0]["clv"] > 0
    # Nakashima drifted (1.55 -> 1.70): 1.60 is below the closing fair value.
    assert out.iloc[1]["clv"] < 0
    assert out.iloc[0]["close_venue"] == "Pinnacle"


def test_settlement_pays_the_logged_odds(rc):
    picks = pd.DataFrame([
        {"match_id": "7", "player": "Cobolli F.", "odds": 2.60},
        {"match_id": "7", "player": "Nakashima B.", "odds": 1.60},
        {"match_id": "9", "player": "Nobody N.", "odds": 3.00},
    ])
    results = pd.DataFrame([
        {"match_id": "7", "player1": "Cobolli F.", "player2": "Nakashima B.", "sets_won1": 2.0, "sets_won2": 0.0},
    ])
    out = rc.settle(picks, results)
    assert out["won"].tolist() == [True, False, None]
    assert out["profit"].tolist()[:2] == pytest.approx([1.60, -1.0])


def test_forecast_sources_are_scored_on_decided_matches(rc):
    log = pd.DataFrame([
        {"taken_at": "2026-10-22T10:00", "match_id": "7", "market_fair_1": 0.7, "model_1": 0.72,
         "ta_elo_1": 0.6, "ta_forecast_1": 0.65, "stats_1": None},
        # Later snapshot of the same match: ignored, the first one counts.
        {"taken_at": "2026-10-22T20:00", "match_id": "7", "market_fair_1": 0.9, "model_1": 0.9,
         "ta_elo_1": 0.9, "ta_forecast_1": 0.9, "stats_1": 0.9},
        {"taken_at": "2026-10-22T10:00", "match_id": "8", "market_fair_1": 0.3, "model_1": 0.35,
         "ta_elo_1": 0.5, "ta_forecast_1": None, "stats_1": 0.4},
        {"taken_at": "2026-10-22T10:00", "match_id": "9", "market_fair_1": 0.5, "model_1": 0.5,
         "ta_elo_1": 0.5, "ta_forecast_1": 0.5, "stats_1": 0.5},   # undecided: dropped
    ])
    results = pd.DataFrame([
        {"match_id": "7", "sets_won1": 2.0, "sets_won2": 0.0},
        {"match_id": "8", "sets_won1": 0.0, "sets_won2": 2.0},
        {"match_id": "9", "sets_won1": 1.0, "sets_won2": 1.0},
    ])
    scores = rc.score_forecasts(log, results)
    allv = scores[scores["scope"] == "all_available"].set_index("source")
    assert allv.loc["market_fair", "n"] == 2
    assert allv.loc["market_fair", "brier"] == pytest.approx(((0.7 - 1) ** 2 + (0.3 - 0) ** 2) / 2)
    assert allv.loc["ta_forecast", "n"] == 1
    # The common scope keeps only matches where every source spoke: none here.
    assert scores[scores["scope"] == "common_matches"].empty
    assert rc.score_forecasts(pd.DataFrame(), results).empty
