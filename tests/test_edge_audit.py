import numpy as np
import pandas as pd
import pytest

from tennissharp import edge_audit


def test_roi_with_significance_flags_noise_as_insignificant():
    # 40 bets at 3.0, won 15 -> ROI +12.5%, but far too few bets to mean anything.
    rng = np.random.default_rng(0)
    won = np.array([1] * 15 + [0] * 25)
    price = np.full(40, 3.0)
    stats = edge_audit.roi_with_significance(won, price)
    assert stats["n_bets"] == 40
    assert stats["roi"] > 0
    assert not stats["significant"]
    assert "zero edge" in stats["interpretation"]


def test_roi_with_significance_detects_a_real_edge():
    # 60% win rate at even money over 5000 bets is a genuine, huge edge.
    won = np.array([1] * 3000 + [0] * 2000)
    price = np.full(5000, 2.0)
    stats = edge_audit.roi_with_significance(won, price)
    assert stats["roi"] == pytest.approx(0.2, abs=1e-9)
    assert stats["significant"]
    assert stats["t_stat"] > 10


def test_roi_with_significance_handles_empty():
    stats = edge_audit.roi_with_significance(np.array([]), np.array([]))
    assert stats["n_bets"] == 0
    assert not stats["significant"]


def test_price_attainability_flags_running_maximum():
    n = 1000
    rng = np.random.default_rng(1)
    true_p = rng.uniform(0.2, 0.8, n)
    # A real book: prices carry a positive margin.
    real_w, real_l = 1 / (true_p * 1.03), 1 / ((1 - true_p) * 1.03)
    # A "max over time" column: inflated enough to imply frequent arbitrage.
    max_w, max_l = 1 / (true_p * 0.98), 1 / ((1 - true_p) * 0.98)
    matches = pd.DataFrame({
        "pinnacle_w": real_w, "pinnacle_l": real_l,
        "market_max_w": max_w, "market_max_l": max_l,
    })
    report = edge_audit.price_attainability_report(matches)
    by_col = report.set_index("price_column")
    assert bool(by_col.loc["pinnacle", "attainable"])
    assert not bool(by_col.loc["market_max", "attainable"])
    assert "NOT ATTAINABLE" in by_col.loc["market_max", "verdict"]


def test_market_calibration_report_on_a_perfectly_calibrated_market():
    rng = np.random.default_rng(2)
    n = 20000
    p = rng.uniform(0.05, 0.95, n)
    winner_wins = rng.random(n) < p
    # Build odds so that the *winner* column always belongs to the actual winner,
    # matching how the real dataset is stored.
    p_winner = np.where(winner_wins, p, 1 - p)
    margin = 1.03
    matches = pd.DataFrame({
        "pinnacle_w": 1 / (p_winner * margin),
        "pinnacle_l": 1 / ((1 - p_winner) * margin),
    })
    cal = edge_audit.market_calibration_report(matches)
    assert not cal.empty
    # A perfectly calibrated market should show small errors in every bucket.
    assert cal.error.abs().max() < 0.05


def test_segment_report_respects_min_bets_and_sorts():
    bets = pd.DataFrame({
        "surface": ["Hard"] * 100 + ["Clay"] * 100 + ["Grass"] * 5,
        "won": [1] * 60 + [0] * 40 + [1] * 40 + [0] * 60 + [1] * 5,
        "price": [2.0] * 205,
    })
    seg = edge_audit.segment_report(bets, by="surface", min_bets=50)
    assert set(seg.surface) == {"Hard", "Clay"}  # Grass dropped: too few bets
    assert seg.iloc[0]["surface"] == "Hard"      # sorted by ROI descending
    assert seg.iloc[0]["roi"] > seg.iloc[1]["roi"]


def test_summarize_incremental_verdict_when_no_information():
    report = pd.DataFrame({
        "season": [2020, 2021], "n": [1000, 1000],
        "market_log_loss": [0.59, 0.59],
        "ours_log_loss": [0.62, 0.62],
        "combined_log_loss": [0.591, 0.591],  # slightly worse than market alone
    })
    summary = edge_audit.summarize_incremental(report)
    assert summary["information_gain"] < 0.001
    assert "NO information beyond the market" in summary["verdict"]


def test_summarize_incremental_verdict_when_information_exists():
    report = pd.DataFrame({
        "season": [2020, 2021], "n": [1000, 1000],
        "market_log_loss": [0.59, 0.59],
        "ours_log_loss": [0.60, 0.60],
        "combined_log_loss": [0.57, 0.57],  # clearly better than market alone
    })
    summary = edge_audit.summarize_incremental(report)
    assert summary["information_gain"] > 0.005
    assert "edge is plausible" in summary["verdict"]
