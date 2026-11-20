import pandas as pd

from tennissharp import te_elo


def _page(rows):
    cols = ["tournament", "tournament_url", "player1", "player1_slug", "odds1", "odds2", "match_id",
            "sets_won1", "time", "player2", "player2_slug", "sets_won2", "score", "date"]
    return pd.DataFrame(rows, columns=cols)


def test_results_keeps_finished_singles_winner_first():
    page = _page([
        ["Futures 2026", "", "A X.", "a", 1.5, 2.5, "1", 0, "10:00", "B Y.", "b", 2, "4-6 3-6", "2026-11-19"],
        ["Sydney ITF", "", "C/D", "c", None, None, "2", 2, "09:00", "E/F", "e", 0, "6-1 6-1", "2026-11-19"],
        ["UTR Pro Tennis Series", "", "G Z.", "g", None, None, "3", None, "11:00", "H W.", "h", None, None,
         "2026-11-19"],
        ["Rome WTA", "/rome-wta/2026/wta-women/", "I V.", "i", 1.2, 4.0, "4", 2, "08:00", "J U.", "j", 1,
         "6-4 3-6 6-2", "2026-11-19"],
    ])
    r = te_elo.results(page)
    assert list(r["match_id"]) == ["4", "1"]          # doubles and unplayed dropped, in time order
    first = r.iloc[1]
    assert (first.winner, first.loser, first.odds_w, first.odds_l, first.level) == ("b", "a", 2.5, 1.5, "ITF")
    assert r.iloc[0].level == "WTA"


def test_levels():
    assert te_elo.level_of("UTR Pro Tennis Series 3") == "UTR"
    assert te_elo.level_of("Futures 2026") == "ITF"
    assert te_elo.level_of("Olbia challenger") == "Challenger"
    assert te_elo.level_of("Rome WTA", "/rome/2026/wta-women/") == "WTA"
    assert te_elo.level_of("Paris") == "ATP"


def _rows(pairs, level="ITF"):
    return pd.DataFrame([{"date": f"2026-01-{i % 28 + 1:02d}", "time": "10:00", "tournament": "x", "level": level,
                          "winner": w, "winner_name": w.upper(), "loser": lo, "loser_name": lo.upper(),
                          "odds_w": 1.5, "odds_l": 2.5, "match_id": str(i)} for i, (w, lo) in enumerate(pairs)])


def test_ratings_learn_and_round_trip():
    r = te_elo.Ratings({"ITF": 1400.0})
    record = []
    r.play(_rows([("a", "b")] * 10), record)
    assert record[0]["p"] == 0.5 and record[0]["n_min"] == 0
    assert r.prob("a", "b") > 0.8 and r.prob("a", "zz") is None
    assert r.players["a"].matches == 10
    back = te_elo.Ratings.from_table(r.table())
    assert abs(back.prob("a", "b") - r.prob("a", "b")) < 1e-3
    assert te_elo.Ratings({"UTR": 1300.0})._get("n", "N", "UTR", "2026-01-01").elo == 1300.0


def test_score_compares_with_market():
    s = te_elo.score([{"p": 0.7, "odds_w": 1.5, "odds_l": 2.5, "n_min": 20},
                      {"p": 0.4, "odds_w": 2.0, "odds_l": 1.8, "n_min": 3}])
    assert s["n"] == 2 and s["hit_rate"] == 0.5
    assert s["with_odds"]["n"] == 2 and s["with_odds"]["market_log_loss"] > 0


def test_fit_scale_recovers_a_line_and_drops_a_wrong_namesake():
    pairs = [(1400 + 10 * i, 100 + 1.1 * (1400 + 10 * i)) for i in range(40)] + [(1500, 3000)]
    a, b = te_elo.fit_scale(pairs)
    assert abs(b - 1.1) < 1e-3 and abs(a - 100) < 0.5
    assert te_elo.fit_scale(pairs[:10]) is None
    assert abs(te_elo.on_ta_scale(1500, (100, 1.1)) - 1750) < 1e-9
