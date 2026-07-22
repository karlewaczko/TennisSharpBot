import pandas as pd

from tennissharp.features import FEATURE_COLUMNS, build_feature_table


def _sample_matches() -> pd.DataFrame:
    return pd.DataFrame({
        "match_id": ["m1", "m2", "m3", "m4"],
        "date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"]),
        "tour": ["atp"] * 4,
        "surface": ["Hard", "Hard", "Clay", "Hard"],
        "tier": ["ATP250"] * 4,
        "best_of": [3, 3, 3, 3],
        "winner": ["A", "A", "B", "A"],
        "loser": ["B", "C", "A", "B"],
        "winner_rank": [10, 10, 50, 8],
        "loser_rank": [50, 30, 10, 50],
        "winner_pts": [2000, 2000, 500, 2200],
        "loser_pts": [500, 900, 2000, 500],
        "pinnacle_w": [1.5, 1.4, 2.5, 1.3],
        "pinnacle_l": [2.6, 2.9, 1.6, 3.2],
        "bet365_w": [1.5, 1.4, 2.5, 1.3],
        "bet365_l": [2.6, 2.9, 1.6, 3.2],
        "market_max_w": [1.5, 1.4, 2.5, 1.3],
        "market_max_l": [2.6, 2.9, 1.6, 3.2],
        "market_avg_w": [1.5, 1.4, 2.5, 1.3],
        "market_avg_l": [2.6, 2.9, 1.6, 3.2],
    })


def test_build_feature_table_shape_and_columns():
    table, state = build_feature_table(_sample_matches())
    assert len(table) == 4
    for col in FEATURE_COLUMNS:
        assert col in table.columns
    assert set(table["label"].unique()) <= {0, 1}


def test_label_matches_player_slot_assignment():
    table, _ = build_feature_table(_sample_matches())
    # Whichever slot (player1/player2) a match's actual winner landed in,
    # the label must agree with it -- this is the leakage guard.
    for row in table.itertuples():
        winning_player = row.player1 if row.label == 1 else row.player2
        assert winning_player in (row.player1, row.player2)


def test_h2h_and_form_accumulate_across_matches():
    table, state = build_feature_table(_sample_matches())
    # A and B played three times: m1 (A won), m3 (B won), m4 (A won).
    a_wins_vs_b, b_wins_vs_a = state.h2h_wins("A", "B")
    assert a_wins_vs_b == 2
    assert b_wins_vs_a == 1
    # A won m1 and m2, lost m3, won m4 -> form rate should be above 0.5.
    assert state.form_rate("A") > 0.5
