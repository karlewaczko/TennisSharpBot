import pandas as pd

from tennissharp.elo import EloRatings, compute_pre_match_ratings, expected_score


def test_expected_score_symmetry():
    assert expected_score(1500, 1500) == 0.5
    assert expected_score(1600, 1500) > 0.5
    assert abs(expected_score(1600, 1500) + expected_score(1500, 1600) - 1.0) < 1e-9


def test_winner_rating_increases_loser_decreases():
    elo = EloRatings()
    before_w, _ = elo.get("A")
    before_l, _ = elo.get("B")
    elo.update("A", "B", "Hard", "ATP250")
    after_w, _ = elo.get("A")
    after_l, _ = elo.get("B")
    assert after_w > before_w
    assert after_l < before_l


def test_upset_gains_more_than_a_coinflip_win():
    # Build up an established favorite (this also raises their K-factor
    # experience, so the challenger below must be equally inexperienced in
    # both scenarios to isolate the "size of the upset" effect from the
    # separate "new players move faster" effect.
    elo = EloRatings()
    for _ in range(30):
        elo.update("Favorite", "Sparring Partner", "Hard", "ATP250")
    fav_before, _ = elo.get("Favorite")
    assert fav_before > 1500.0

    elo.update("Challenger", "Favorite", "Hard", "ATP250")
    upset_gain, _ = elo.get("Challenger")
    upset_gain -= 1500.0

    elo2 = EloRatings()
    elo2.update("X", "Y", "Hard", "ATP250")  # both start at 1500: a coinflip win
    coinflip_gain, _ = elo2.get("X")
    coinflip_gain -= 1500.0

    assert upset_gain > coinflip_gain


def test_compute_pre_match_ratings_no_leakage():
    matches = pd.DataFrame({
        "winner": ["A", "B", "A"],
        "loser": ["B", "A", "B"],
        "surface": ["Hard", "Hard", "Hard"],
        "tier": ["ATP250", "ATP250", "ATP250"],
    })
    enriched, _ = compute_pre_match_ratings(matches)
    # Before any match, both players are at the default rating.
    assert enriched.loc[0, "winner_elo_overall"] == 1500.0
    assert enriched.loc[0, "loser_elo_overall"] == 1500.0
    # By the third match, A (won match 1, lost match 2) should reflect that history.
    assert enriched.loc[2, "winner_elo_overall"] != 1500.0


def test_normalize_surface_maps_the_known_names():
    from tennissharp.elo import normalize_surface
    assert normalize_surface("hard") == "Hard"
    assert normalize_surface("Clay") == "Clay"
    assert normalize_surface(" GRASS ") == "Grass"
    assert normalize_surface("indoor hard") == "Hard"


def test_normalize_surface_rejects_the_sites_placeholder():
    """TennisExplorer writes "-" when an event lists no surface. It is truthy,
    so it sails through any `or` fallback, and EloRatings.get then returns the
    1500 default for BOTH players -- elo_surface_diff becomes exactly zero
    with nothing logged."""
    from tennissharp.elo import normalize_surface
    assert normalize_surface("-") is None
    assert normalize_surface("") is None
    assert normalize_surface(None) is None
    assert normalize_surface("Indoors") is None


def test_an_unknown_surface_silently_returns_the_default_rating():
    """Pins the trap normalize_surface exists to keep callers away from:
    `get` does not raise on a surface it does not track."""
    from tennissharp.elo import EloRatings, DEFAULT_RATING
    elo = EloRatings()
    elo.update("A", "B", "Hard", None)
    _, on_hard = elo.get("A", "Hard")
    _, on_junk = elo.get("A", "-")
    assert on_hard != DEFAULT_RATING
    assert on_junk == DEFAULT_RATING
