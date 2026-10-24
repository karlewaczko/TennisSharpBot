"""Serve/return profiles from Sackmann-schema matches and the point model."""
import pandas as pd
import pytest

from tennissharp import player_stats as ps


def _matches():
    base = {"tournament": "Lyon", "surface": "Hard", "tier": "250", "best_of": 3, "source_tour": "atp",
            "winner_rank": 20, "loser_rank": 40}
    rows = []
    for i in range(12):
        rows.append({**base, "date": pd.Timestamp("2026-10-01") + pd.Timedelta(days=i),
                     "winner": "Jannik Sinner", "loser": "Daniel Altmaier",
                     "winner_ace": 10, "winner_df": 2, "winner_svpt": 60, "winner_1stin": 40,
                     "winner_1stwon": 32, "winner_2ndwon": 12, "winner_svgms": 10,
                     "winner_bpsaved": 2, "winner_bpfaced": 3,
                     "loser_ace": 3, "loser_df": 4, "loser_svpt": 70, "loser_1stin": 42,
                     "loser_1stwon": 28, "loser_2ndwon": 12, "loser_svgms": 10,
                     "loser_bpsaved": 4, "loser_bpfaced": 8})
    return pd.DataFrame(rows)


def test_profile_reads_serve_and_return_from_both_sides():
    book = ps.StatBook(_matches(), as_of="2026-10-20")
    s = book.stats("Jannik Sinner", "Hard")
    o = s["overall"]
    assert o["matches"] == 12 and o["wins"] == 12
    assert o["spw"] == pytest.approx(44 / 60)
    assert o["rpw"] == pytest.approx((70 - 40) / 70)
    assert o["hold_pct"] == pytest.approx(1 - 1 / 10)
    assert o["break_pct"] == pytest.approx(4 / 10)
    assert s["surface"]["matches"] == 12       # 12 >= MIN_SURFACE_MATCHES
    assert s["form10"] == (10, 0)
    assert s["rank"] == 20
    loser = book.stats("Daniel Altmaier")
    assert loser["overall"]["losses"] == 12 and loser["form10"] == (0, 10)


def test_resolve_maps_schedule_names_and_prefers_the_busier_namesake():
    m = _matches()
    extra = m.iloc[[0]].copy()
    extra["winner"] = "Jan Sinner"
    book = ps.StatBook(pd.concat([m, extra]), as_of="2026-10-20")
    assert book.resolve("Sinner J.") == "Jannik Sinner"
    assert book.resolve("Altmaier D.") == "Daniel Altmaier"
    assert book.resolve("Nobody X.") is None


def test_head_to_head_counts_both_directions():
    book = ps.StatBook(_matches(), as_of="2026-10-20")
    assert book.head_to_head("Jannik Sinner", "Daniel Altmaier")["wins_a"] == 12
    assert book.head_to_head("Daniel Altmaier", "Jannik Sinner")["wins_b"] == 12


def test_window_drops_old_matches():
    book = ps.StatBook(_matches(), as_of="2028-01-01")
    assert book.stats("Jannik Sinner") is None


def test_game_probability_known_values():
    assert ps.game_probability(0.5) == pytest.approx(0.5)
    assert ps.game_probability(0.6) == pytest.approx(0.7357, abs=1e-3)
    assert ps.game_probability(0.7) > ps.game_probability(0.6)


def test_tiebreak_set_and_match_are_symmetric_and_monotonic():
    assert ps.tiebreak_probability(0.62, 0.62) == pytest.approx(0.5, abs=1e-9)
    assert ps.set_probability(0.62, 0.62) == pytest.approx(0.5, abs=1e-9)
    assert ps.match_probability(0.62, 0.62) == pytest.approx(0.5, abs=1e-9)
    assert ps.match_probability(0.65, 0.60) > 0.5
    assert ps.match_probability(0.65, 0.60, best_of=5) > ps.match_probability(0.65, 0.60, best_of=3)
    assert ps.match_probability(0.60, 0.65) == pytest.approx(1 - ps.match_probability(0.65, 0.60), abs=1e-9)


def test_point_probabilities_follow_barnett_clarke():
    p_a, p_b = ps.point_probabilities(0.66, 0.40, 0.62, 0.38, tour_avg=0.64)
    # p_a = 0.64 + (0.66 - 0.64) - (0.38 - 0.36)
    assert p_a == pytest.approx(0.64)
    assert p_b == pytest.approx(0.64 + (0.62 - 0.64) - (0.40 - 0.36))


def test_stat_forecast_shrinks_thin_profiles_toward_the_average():
    book = ps.StatBook(_matches(), as_of="2026-10-20")
    a = book.stats("Jannik Sinner", "Hard")
    b = book.stats("Daniel Altmaier", "Hard")
    p = ps.stat_forecast(a, b, tour_avg=0.64)
    assert 0.5 < p < 1.0
    thin = {"overall": {"with_stats": 1, "spw": 0.90, "rpw": 0.60}, "surface": None}
    s, r = ps.blended_rates(thin, 0.64)
    assert 0.64 < s < 0.70           # one match barely moves the average


def test_leader_tables_have_the_api_schema():
    book = ps.StatBook(_matches(), as_of="2026-10-20")
    tables = ps.leader_tables(book, "atp", "top50", min_matches=5)
    assert list(tables["all"].columns) == ps.SERVE_LEADER_COLUMNS
    assert list(tables["return_hard"].columns) == ps.RETURN_LEADER_COLUMNS
    assert tables["all"]["player"].tolist() == ["Jannik Sinner", "Daniel Altmaier"]
    assert tables["clay"].empty


def test_one_player_spelled_two_ways_is_one_profile():
    m = _matches()
    variant = m.iloc[[0, 1]].copy()
    variant["winner"] = "Jannik  sinner "      # case and spacing differ
    book = ps.StatBook(pd.concat([m, variant], ignore_index=True), as_of="2026-10-20")
    assert "Jannik  sinner " not in book.players
    assert book.stats("Jannik Sinner")["overall"]["matches"] == 14
    names = ps.canonical_names(pd.DataFrame({"winner": ["Alex de Minaur"] * 3 + [" Alex De Minaur"],
                                             "loser": ["X"] * 4}))
    assert names[" Alex De Minaur"] == "Alex de Minaur"
