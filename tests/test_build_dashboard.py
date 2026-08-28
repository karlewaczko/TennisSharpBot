"""Guards on what reaches the published value table.

The schedule feed doubles as the results feed: a finished match keeps its
pre-match odds, so nothing in the odds columns tells it apart from an
upcoming one. That is how `Fritz T. vs Nakashima B.` (6-3 3-6 6-3) ended up
as the card's only "signal" on a page meant to be shown to someone.
"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_SCRIPTS = Path(__file__).parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location("build_dashboard",
                                                _SCRIPTS / "build_dashboard.py")


@pytest.fixture(scope="module")
def bd():
    sys.path.insert(0, str(_SCRIPTS))
    try:
        mod = importlib.util.module_from_spec(_SPEC)
        _SPEC.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(_SCRIPTS))


def _card():
    """One finished, one in-play, one retirement, one upcoming -- all four
    spellings taken from a single real fetch of tennisexplorer_upcoming.csv."""
    return pd.DataFrame([
        {"player1": "Fritz T.", "player2": "Nakashima B.", "odds1": 1.53,
         "odds2": 2.50, "score": "6-3 3-6 6-3", "sets_won1": 2.0, "sets_won2": 1.0},
        {"player1": "Quevedo K.", "player2": "Jones F.", "odds1": 1.98,
         "odds2": 1.78, "score": None, "sets_won1": 1.0, "sets_won2": 0.0},
        {"player1": "Retired A.", "player2": "Retired B.", "odds1": 2.10,
         "odds2": 1.70, "score": "2-1", "sets_won1": None, "sets_won2": None},
        {"player1": "Sinner J.", "player2": "Alcaraz C.", "odds1": 1.80,
         "odds2": 2.00, "score": None, "sets_won1": None, "sets_won2": None},
    ])


def test_finished_matches_never_reach_the_table(bd):
    left = _card()[bd.unplayed_mask(_card())]
    assert left["player1"].tolist() == ["Sinner J."]


def test_a_running_match_counts_as_started(bd):
    """The first set is under way: `score` is still empty, only the set count
    is filled. Checking `score` alone would publish a live match as value."""
    running = _card().iloc[[1]]
    assert not bd.unplayed_mask(running).any()


def test_a_retirement_counts_as_started(bd):
    """Decided inside the opening set: games are recorded, sets_won is not.
    Checking the set count alone would miss it."""
    retired = _card().iloc[[2]]
    assert not bd.unplayed_mask(retired).any()


def test_mask_keeps_the_frames_index(bd):
    """It is used to subset `sched` directly; a reset index would misalign."""
    card = _card().iloc[[1, 3]]
    mask = bd.unplayed_mask(card)
    assert list(mask.index) == [1, 3]
    assert card[mask]["player1"].tolist() == ["Sinner J."]


def test_a_feed_without_result_columns_is_not_dropped_wholesale(bd):
    """An older CSV predating the score capture has no markers at all. Those
    rows are unknown, not finished -- dropping them would empty the page."""
    bare = pd.DataFrame([{"player1": "A", "player2": "B", "odds1": 2.0, "odds2": 1.8}])
    assert bd.unplayed_mask(bare).all()


def test_placeholder_prices_are_not_a_market(bd):
    """TennisExplorer lists 1.02/1.02 and 1.03/1.03 for matches nobody has
    priced yet -- a 94-96 % overround. De-vigged, one of those produced a
    -60.8 % EV on Vidmanova out of nothing at all."""
    assert not bd.is_priced([1.02, 1.02])
    assert not bd.is_priced([1.03, 1.03])
    assert not bd.is_priced([1.08, 1.33])


def test_real_two_way_prices_survive(bd):
    """Pinnacle runs 2-3 %, the softest books into the teens; the median on a
    full card is 10 %. None of that may be filtered out."""
    assert bd.is_priced([1.88, 2.02])      # Pinnacle, ~2 %
    assert bd.is_priced([1.23, 4.16])      # soft, ~5 %
    assert bd.is_priced([1.60, 1.72])      # ~21 %, high but a real quote pair
    assert bd.margin([1.88, 2.02]) < 0.03


def test_impossible_odds_are_rejected(bd):
    """1.0 pays nothing back and a negative overround is a scrape artefact,
    not an arbitrage -- both sides come from one book."""
    assert not bd.is_priced([1.0, 5.0])
    assert not bd.is_priced([2.10, 2.10])  # margin -4.8 %
    assert not bd.is_priced([None, 2.0])


def test_the_margin_ceiling_sits_above_every_real_book(bd):
    assert 0.15 < bd.MAX_REF_MARGIN < 0.5


def test_mens_grand_slams_are_best_of_five(bd):
    """`best_of` is a trained feature -- over five sets the same Elo gap
    converts to a higher win probability. Every match was scored as
    best-of-three until the US Open put 104 five-setters on the card."""
    assert bd.best_of_for("US Open", "atp") == 5
    assert bd.best_of_for("Wimbledon", "atp") == 5
    assert bd.best_of_for("Roland Garros", "atp") == 5


def test_women_play_three_sets_at_the_majors(bd):
    assert bd.best_of_for("US Open", "wta") == 3
    assert bd.best_of_for("Australian Open", "wta") == 3


def test_everything_else_stays_best_of_three(bd):
    assert bd.best_of_for("Winston Salem", "atp") == 3
    assert bd.best_of_for("Augsburg challenger", "atp") == 3
    assert bd.best_of_for("Monterrey", "wta") == 3


def test_grand_slam_qualifying_is_best_of_three(bd):
    """The men's majors play five sets in the main draw only. Qualifying
    carries the same tournament name and URL on the schedule page, so reading
    the name alone scored 70 finished US Open qualifiers as five-setters."""
    assert bd.best_of_for("US Open", "atp", is_qualifying=True) == 3
    assert bd.best_of_for("Wimbledon", "atp", is_qualifying=True) == 3
    # The main draw is unaffected.
    assert bd.best_of_for("US Open", "atp", is_qualifying=False) == 5
