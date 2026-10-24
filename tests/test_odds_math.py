import pytest

from tennissharp.odds_math import (
    edge, expected_value, implied_probability, multiplicative_devig,
    overround, shin_devig,
)


def test_implied_probability():
    assert implied_probability(2.0) == pytest.approx(0.5)
    assert implied_probability(4.0) == pytest.approx(0.25)


def test_overround_positive_for_real_bookmaker_odds():
    # Typical Pinnacle-style tight market: ~2-3% margin
    assert overround([1.95, 1.95]) == pytest.approx(0.0256, abs=1e-3)


def test_multiplicative_devig_sums_to_one():
    probs = multiplicative_devig([1.90, 1.90])
    assert sum(probs) == pytest.approx(1.0)
    assert probs[0] == pytest.approx(probs[1])


def test_shin_devig_sums_to_one_and_reduces_favorite_longshot_bias():
    odds = [1.50, 3.00]
    fair = shin_devig(odds)
    assert sum(fair) == pytest.approx(1.0, abs=1e-6)
    # Favorite (lower odds) should still have the higher fair probability.
    assert fair[0] > fair[1]


def test_shin_devig_no_margin_returns_raw_probabilities():
    # Odds implying exactly 100% (no overround) should pass through unchanged.
    fair = shin_devig([2.0, 2.0])
    assert fair[0] == pytest.approx(0.5)
    assert fair[1] == pytest.approx(0.5)


def test_edge_and_expected_value():
    assert edge(0.55, 0.50) == pytest.approx(0.05)
    assert expected_value(0.55, 2.0) == pytest.approx(0.10)
    assert expected_value(0.40, 2.0) == pytest.approx(-0.20)
