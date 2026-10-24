import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_SCRIPTS = Path(__file__).parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location("study_line_movement", _SCRIPTS / "study_line_movement.py")


@pytest.fixture(scope="module")
def lm():
    sys.path.insert(0, str(_SCRIPTS))
    try:
        mod = importlib.util.module_from_spec(_SPEC)
        _SPEC.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(_SCRIPTS))


def test_open_close_reads_the_marked_opening_and_the_last_change(lm):
    hist = pd.DataFrame([
        {"bookmaker": "Pinnacle", "player": "A", "timestamp": pd.Timestamp("2026-10-21 10:00"), "odds": 1.80, "is_opening": True},
        {"bookmaker": "Pinnacle", "player": "A", "timestamp": pd.Timestamp("2026-10-22 09:00"), "odds": 1.70, "is_opening": False},
        {"bookmaker": "Pinnacle", "player": "A", "timestamp": pd.Timestamp("2026-10-22 12:00"), "odds": 1.65, "is_opening": False},
        {"bookmaker": "Pinnacle", "player": "B", "timestamp": pd.Timestamp("2026-10-21 10:00"), "odds": 2.05, "is_opening": True},
        {"bookmaker": "Pinnacle", "player": "B", "timestamp": pd.Timestamp("2026-10-22 12:00"), "odds": 2.30, "is_opening": False},
    ])
    oc = lm.open_close(hist)
    assert oc["Pinnacle"]["A"] == (1.80, 1.65)
    assert oc["Pinnacle"]["B"] == (2.05, 2.30)


def test_analysis_reports_movement_clv_and_soft_value(lm):
    records = [
        # Favourite shortened 0.55 -> 0.60 and won: opening favourite price carried CLV.
        {"pin_open_fav": 1.80, "pin_open_dog": 2.10, "pin_close_fav": 1.65,
         "pin_open_fav_prob": 0.55, "pin_close_fav_prob": 0.60, "fav_won": True,
         "soft_sides_checked": 2, "soft_sides_positive": 1, "soft_pos_evs": [0.02],
         "soft_best": {"ev": 0.02, "book": "bet365"}},
        {"pin_open_fav": 1.50, "pin_open_dog": 2.70, "pin_close_fav": 1.57,
         "pin_open_fav_prob": 0.66, "pin_close_fav_prob": 0.63, "fav_won": False,
         "soft_sides_checked": 2, "soft_sides_positive": 0, "soft_pos_evs": [], "soft_best": None},
    ]
    res = lm.analyse(records)
    assert res["n_matches"] == 2
    pin = res["pinnacle"]
    assert pin["favourite_shortened_share"] == 0.5
    assert pin["clv_open_favourite"] == pytest.approx(((1.80 * 0.60 - 1) + (1.50 * 0.63 - 1)) / 2, abs=1e-4)
    assert pin["roi_open_favourite"] == pytest.approx((0.80 - 1.0) / 2, abs=1e-4)
    assert res["soft_at_close"]["share_above_fair"] == 0.25
    assert res["soft_at_close"]["best_side"]["book"] == "bet365"


def test_empty_study_does_not_crash(lm):
    assert lm.analyse([]) == {"n_matches": 0}
