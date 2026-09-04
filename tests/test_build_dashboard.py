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


def test_a_soft_book_row_is_shown_but_never_signalled(bd):
    """The model's market feature is Pinnacle's de-vigged price and training
    drops rows without one. Over 20 000 historical matches carrying both,
    Pinnacle and the average book differ by 0.63 percentage points at the
    median -- the size of the edge being measured."""
    assert "Pinnacle" in bd.SHARP_BOOKS and "Betfair" in bd.SHARP_BOOKS
    assert "TennisExplorer" not in bd.SHARP_BOOKS
    assert "bet365" not in bd.SHARP_BOOKS


def test_the_signal_threshold_is_ev_not_edge(bd):
    """The brief is "bet at +5% EV". Edge is (forecast - market), an exact
    mirror between the sides; EV is that edge converted at the side's own
    price. Mannarino at 3.85 carried +5.23% EV on a 3.41 point edge, while
    the same edge on a 1.30 shot is worth +1.1%. Thresholding on edge asked
    far more of a longshot than of a favourite."""
    src = (_SCRIPTS / "build_dashboard.py").read_text()
    signal_block = src.split('"signal": (', 1)[1].split("),", 1)[0]
    assert "ev_at_ref" in signal_block
    assert "edge" not in signal_block


def test_audit_numbers_prefer_the_measured_file(bd, tmp_path, monkeypatch):
    """The page publishes these. They were literals here until a data refresh
    moved the information gain to -0.00111 and the page kept claiming the old
    -0.00078 for days."""
    import json as _json
    from tennissharp import config
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    (tmp_path / "edge_audit_summary.json").write_text(_json.dumps(
        {"information_gain": -0.00222, "matches_tested": 99, "measured_at": "2026-09-01T00:00:00+00:00"}))
    got = bd.audit_numbers()
    assert got["information_gain"] == -0.00222
    assert got["matches_tested"] == 99
    assert got["measured_at"] == "2026-09-01T00:00:00+00:00"


def test_audit_numbers_fall_back_when_the_file_is_absent(bd, tmp_path, monkeypatch):
    from tennissharp import config
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    got = bd.audit_numbers()
    assert got["information_gain"] == bd.AUDIT_FALLBACK["information_gain"]
    assert "backtest_roi" in got


def test_orientation_resolves_both_names(bd):
    assert bd.orientation(["Pegula Jessica", "Fernandez Leylah"],
                          "Pegula J.", "Fernandez L.A.") is True
    assert bd.orientation(["Fernandez Leylah", "Pegula Jessica"],
                          "Pegula J.", "Fernandez L.A.") is False


def test_orientation_refuses_to_guess(bd):
    """The old test read a failed resolution as "first is a" and left the
    prices where they lay. Pegula got her opponent's 5.30 instead of her own
    1.15 -- a 95% favourite scored as a 19% outsider, in the model's input as
    well as on the page."""
    assert bd.orientation(["Nobody At All", "Pegula Jessica"],
                          "Pegula J.", "Fernandez L.A.") is None
    assert bd.orientation(["Pegula Jessica", "Nobody At All"],
                          "Pegula J.", "Fernandez L.A.") is None


def test_orientation_refuses_when_both_names_hit_the_same_player(bd):
    assert bd.orientation(["Pegula Jessica", "Pegula J."],
                          "Pegula J.", "Fernandez L.A.") is None


class _FakeState:
    def __init__(self, stale_players):
        self._stale = set(stale_players)

    def is_stale(self, player, as_of):
        return player in self._stale


def test_a_player_active_elsewhere_is_no_longer_stale(bd):
    """Our feed carries no challengers or qualifying, so it loses sight of
    players who are competing there every week. On the card that first
    carried this check, 7 of the 8 players marked stale had played within
    three weeks according to TennisMyLife."""
    today = pd.Timestamp("2026-09-04")
    recent = {"Thiago Seyboth Wild": pd.Timestamp("2026-08-26")}
    assert not bd.still_stale("Seyboth Wild T.", _FakeState(["Seyboth Wild T."]),
                              today, recent, list(recent))


def test_a_genuinely_absent_player_stays_stale(bd):
    today = pd.Timestamp("2026-09-04")
    recent = {"Carlos Alcaraz": pd.Timestamp("2026-04-15")}
    assert bd.still_stale("Alcaraz C.", _FakeState(["Alcaraz C."]),
                          today, recent, list(recent))


def test_an_unknown_player_stays_stale(bd):
    today = pd.Timestamp("2026-09-04")
    assert bd.still_stale("Nobody X.", _FakeState(["Nobody X."]), today,
                          {"Carlos Alcaraz": today}, ["Carlos Alcaraz"])


def test_a_current_player_is_never_marked_by_the_override(bd):
    """The second source may only clear a flag, never raise one."""
    today = pd.Timestamp("2026-09-04")
    assert not bd.still_stale("Sinner J.", _FakeState([]), today, {}, [])


def test_without_the_index_the_original_answer_stands(bd):
    today = pd.Timestamp("2026-09-04")
    assert bd.still_stale("Smith C.", _FakeState(["Smith C."]), today, {}, [])
