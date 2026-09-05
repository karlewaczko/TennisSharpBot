import pytest

from tennissharp.staking import full_kelly_fraction, stake_size


def test_full_kelly_zero_at_fair_odds():
    # If decimal odds exactly match true probability (no edge), Kelly stakes 0.
    assert full_kelly_fraction(0.5, 2.0) == pytest.approx(0.0, abs=1e-9)


def test_full_kelly_positive_with_edge():
    # 55% true win probability at fair (2.0) odds is a real edge.
    f = full_kelly_fraction(0.55, 2.0)
    assert f == pytest.approx(0.10, abs=1e-9)


def test_full_kelly_negative_without_edge_clamped_to_zero_stake():
    f = full_kelly_fraction(0.40, 2.0)
    assert f < 0
    assert stake_size(10_000, 0.40, 2.0) == 0.0


def test_stake_size_respects_fraction_and_cap():
    bankroll = 10_000
    stake = stake_size(bankroll, 0.55, 2.0, kelly_fraction=0.25, max_stake_fraction=0.05)
    full = full_kelly_fraction(0.55, 2.0)
    expected = bankroll * min(full * 0.25, 0.05)
    assert stake == pytest.approx(expected)


def test_stake_size_never_exceeds_max_stake_fraction():
    # A huge, unrealistic edge should still be capped for bankroll safety.
    stake = stake_size(10_000, 0.99, 1.05, kelly_fraction=1.0, max_stake_fraction=0.05)
    assert stake <= 10_000 * 0.05 + 1e-6
