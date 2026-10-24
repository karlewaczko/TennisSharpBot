import pandas as pd
import pytest

from tennissharp.backtest import run_backtest


def _tiny_matches() -> pd.DataFrame:
    # Content doesn't matter -- the guardrails must fire before any modelling.
    return pd.DataFrame({
        "match_id": ["m1"], "date": pd.to_datetime(["2024-01-01"]), "tour": ["atp"],
        "surface": ["Hard"], "tier": ["ATP250"], "best_of": [3],
        "tournament": ["Test"], "winner": ["A"], "loser": ["B"],
        "winner_rank": [1], "loser_rank": [2], "winner_pts": [100], "loser_pts": [50],
        "pinnacle_w": [1.5], "pinnacle_l": [2.6],
        "market_avg_w": [1.5], "market_avg_l": [2.6],
        "market_max_w": [1.6], "market_max_l": [2.8],
    })


def test_refuses_to_bet_the_non_attainable_max_column():
    with pytest.raises(ValueError, match="running maximum"):
        run_backtest(_tiny_matches(), bet_price_col="market_max")


def test_refuses_to_price_a_book_against_itself():
    with pytest.raises(ValueError, match="against itself"):
        run_backtest(_tiny_matches(), bet_price_col="pinnacle", reference_col="pinnacle")


def test_error_message_names_a_safe_alternative():
    with pytest.raises(ValueError) as exc:
        run_backtest(_tiny_matches(), bet_price_col="market_max")
    assert "market_avg" in str(exc.value)
