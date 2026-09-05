import pandas as pd

from tennissharp.elo import EloRatings
from tennissharp.features import LiveState
from tennissharp.value_finder import find_value_bets


class _StubModel:
    """Always gives the home/player1 side a fixed win probability, so tests
    can drive edge/no-edge cases deterministically without a real classifier.
    """
    def __init__(self, prob_a: float):
        self.prob_a = prob_a

    def predict_proba(self, X):
        n = len(X)
        return pd.DataFrame({0: [1 - self.prob_a] * n, 1: [self.prob_a] * n}).to_numpy()


def _make_state() -> LiveState:
    elo = EloRatings()
    elo.update("Djokovic N.", "Nadal R.", "Hard", "ATP250")  # just to populate both players
    return LiveState(elo=elo)


def _make_event(home="Novak Djokovic", away="Rafael Nadal", home_odds=1.5, away_odds=2.8):
    return {
        "home_team": home,
        "away_team": away,
        "commence_time": "2026-08-01T12:00:00Z",
        "bookmakers": [{
            "title": "TestBook",
            "markets": [{
                "key": "h2h",
                "outcomes": [
                    {"name": home, "price": home_odds},
                    {"name": away, "price": away_odds},
                ],
            }],
        }],
    }


def test_find_value_bets_does_not_crash_and_uses_all_feature_columns():
    # Regression test: FEATURE_COLUMNS includes tourney_surface_speed, which
    # earlier crashed value_finder with a KeyError since the live feature
    # builder didn't supply it.
    state = _make_state()
    model = _StubModel(prob_a=0.9)  # model thinks home is a big favorite
    events = [_make_event(home_odds=1.5, away_odds=2.8)]  # market roughly agrees -> no edge
    bets = find_value_bets(state, model, events, edge_threshold=0.03)
    assert isinstance(bets, pd.DataFrame)


def test_find_value_bets_flags_a_real_disagreement():
    state = _make_state()
    # Model is confident the home player wins; market odds imply the away
    # player is the favorite -- a clear disagreement above any threshold.
    model = _StubModel(prob_a=0.85)
    events = [_make_event(home_odds=3.0, away_odds=1.4)]
    bets = find_value_bets(state, model, events, edge_threshold=0.03)
    assert len(bets) == 1
    assert bets.iloc[0]["player"] == "Djokovic N."


def test_unmatched_players_are_skipped_not_crashed():
    state = _make_state()
    model = _StubModel(prob_a=0.6)
    events = [_make_event(home="Some Unknown Player", away="Another Unknown Player")]
    bets = find_value_bets(state, model, events, edge_threshold=0.03)
    assert bets.empty
