"""The scored probability must not depend on which player is listed first.

Every feature is a difference (a minus b) and the market feature is a's
logit, so swapping the pair negates the whole input vector. A model that had
learned that antisymmetry would return exactly 1 - p. A gradient boosting
ensemble does not: it splits on raw thresholds and lands in different leaves.
On a 93-match US Open card the two orderings disagreed by 1.5 percentage
points at the median and 4.7 at the worst, and the sign of the edge flipped
on 38 of 88 matches -- against a median edge of 0.90 points.
"""
import numpy as np
import pandas as pd
import pytest

from tennissharp.features import LiveState
from tennissharp.value_finder import matchup_probability


class _AsymmetricModel:
    """Stands in for the trained ensemble: it reads one feature and applies a
    hard threshold, so it is deliberately not antisymmetric."""

    def predict_proba(self, X):
        diff = float(X["elo_overall_diff"].iloc[0])
        p = 0.75 if diff > 0 else 0.30
        return np.array([[1 - p, p]])


@pytest.fixture
def state():
    st = LiveState.__new__(LiveState)
    st.elo = _Elo()
    st.last_rank_pts = {"A": 2000, "B": 1000}
    st.form = {"A": [1, 1, 0], "B": [0, 0, 1]}
    st.h2h = {}
    st.last_seen = {"A": pd.Timestamp("2026-08-20"), "B": pd.Timestamp("2026-08-21")}
    st.recent_dates = {"A": [], "B": []}
    st.last_surface = {"A": "Hard", "B": "Hard"}
    return st


class _Elo:
    RATINGS = {"A": (1800.0, 1790.0), "B": (1600.0, 1610.0)}

    def get(self, player, surface):
        return self.RATINGS.get(player, (1500.0, 1500.0))


def test_the_two_orderings_agree_exactly(state):
    model = _AsymmetricModel()
    p_ab = matchup_probability(model, state, "A", "B", "Hard", 3, market_prob_a=0.62)
    p_ba = matchup_probability(model, state, "B", "A", "Hard", 3, market_prob_a=0.38)
    assert p_ab + p_ba == pytest.approx(1.0, abs=1e-12)


def test_the_raw_model_really_is_asymmetric(state):
    """Guards the premise: if the stand-in were symmetric the test above
    would pass for the wrong reason."""
    model = _AsymmetricModel()
    cols_a = {"elo_overall_diff": 200.0}
    cols_b = {"elo_overall_diff": -200.0}
    pa = model.predict_proba(pd.DataFrame([cols_a]))[0][1]
    pb = model.predict_proba(pd.DataFrame([cols_b]))[0][1]
    assert pa + pb != pytest.approx(1.0)


def test_it_sits_between_the_two_one_way_answers(state):
    model = _AsymmetricModel()
    p = matchup_probability(model, state, "A", "B", "Hard", 3, market_prob_a=0.62)
    assert 0.30 <= p <= 0.75


def test_it_works_without_a_market_price(state):
    """The no-market model has one fewer column; the averaging must still
    hold together."""
    model = _AsymmetricModel()
    p_ab = matchup_probability(model, state, "A", "B", "Hard", 3)
    p_ba = matchup_probability(model, state, "B", "A", "Hard", 3)
    assert p_ab + p_ba == pytest.approx(1.0, abs=1e-12)


def test_a_symmetric_model_is_left_untouched(state):
    """Averaging must not distort a model that is already antisymmetric."""

    class _Symmetric:
        def predict_proba(self, X):
            d = float(X["elo_overall_diff"].iloc[0])
            p = 1 / (1 + np.exp(-d / 400))
            return np.array([[1 - p, p]])

    direct = _Symmetric().predict_proba(pd.DataFrame([{"elo_overall_diff": 200.0}]))[0][1]
    p = matchup_probability(_Symmetric(), state, "A", "B", "Hard", 3)
    assert p == pytest.approx(direct, abs=1e-9)
