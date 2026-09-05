"""Structural checks on the stored Tennis Abstract Elo tables.

The scrape reads an HTML table whose column order the site can change without
notice; a silent shift would mis-assign ratings across the whole file while
still producing a plausible-looking CSV. That is what these tests exist to
catch.

They used to catch it by pinning exact ratings transcribed from the published
leaderboards. That does not work against a live table: Tennis Abstract
recomputes after every tournament, so the pins went red on a legitimate
refresh (the US Open alone moved Djokovic 1975.5 -> 2061.0 and Sabalenka
2194.6 -> 2180.9) and a red build then said nothing about whether the parse
was still correct. A test that fails on correct data cannot report a fault.

The invariants below hold for every edition of the table and break under
exactly the failure being guarded against -- a shifted or truncated parse.

Skips rather than fails when the files are absent -- they are refreshed by
scripts/update_data.py and a clean checkout may not have run it yet.
"""
import pandas as pd
import pytest

from tennissharp import config

# Players who have been rated for years and will not vanish between updates.
# Their presence is what a truncated or mis-keyed parse loses first.
ANCHORS = {"atp": ["Jannik Sinner", "Carlos Alcaraz", "Novak Djokovic"],
           "wta": ["Aryna Sabalenka", "Elena Rybakina"]}
# The published tables have run 500-600 rows per tour for years. A parse that
# grabbed the wrong table, or stopped early, lands far outside this.
PLAUSIBLE_ROWS = (350, 800)


def _load(tour: str) -> pd.DataFrame:
    path = config.PROCESSED_DIR / f"ta_elo_{tour}_general.csv"
    if not path.exists():
        pytest.skip(f"{path.name} fehlt -- scripts/update_data.py noch nicht gelaufen")
    return pd.read_csv(path)


@pytest.mark.parametrize("tour", ["wta", "atp"])
def test_rating_falls_with_rank(tour):
    """The decisive check. `elo_rank` is the site's own ordering by `elo`, so
    the two columns must agree row by row -- and they stop agreeing the moment
    a column shift puts some other number in the `elo` position."""
    df = _load(tour).sort_values("elo_rank")
    elo = df["elo"].tolist()
    for higher, lower in zip(elo, elo[1:]):
        assert higher >= lower - 1e-9, f"elo steigt bei fallendem Rang ({higher} -> {lower})"


@pytest.mark.parametrize("tour", ["wta", "atp"])
def test_table_is_complete_and_rank_ordered(tour):
    """A truncated scrape still parses; a contiguous rank sequence catches it.
    The row count moves between editions, so it is bounded, not pinned."""
    df = _load(tour)
    assert PLAUSIBLE_ROWS[0] <= len(df) <= PLAUSIBLE_ROWS[1]
    ranks = df["elo_rank"].dropna().astype(int).tolist()
    assert ranks == sorted(ranks)
    assert ranks[0] == 1 and ranks[-1] == len(df)


@pytest.mark.parametrize("tour", ["wta", "atp"])
def test_the_long_standing_names_are_present(tour):
    df = _load(tour).set_index("player")
    for player in ANCHORS[tour]:
        assert player in df.index, f"{player} fehlt in ta_elo_{tour}_general.csv"


@pytest.mark.parametrize("tour", ["wta", "atp"])
def test_ratings_sit_on_the_elo_scale(tour):
    """Ratings run roughly 1000-2400. A shift that pulled in age (15-42) or
    the official ranking (1-1500) would leave this band immediately."""
    df = _load(tour)
    assert df["elo"].between(800, 2600).all()
    assert df["elo"].max() > 2000, "kein Spieler auf Weltklasse-Niveau -- falsche Spalte?"


@pytest.mark.parametrize("tour", ["wta", "atp"])
def test_surface_splits_are_present_and_plausible(tour):
    """hElo/cElo/gElo are blends of overall and surface-only ratings, so they
    track the overall number closely -- a column shift would break that."""
    df = _load(tour)
    for col in ("helo", "celo", "gelo"):
        assert col in df.columns
        paired = df[["elo", col]].dropna()
        assert len(paired) > 100
        assert paired["elo"].corr(paired[col]) > 0.85, f"{col} korreliert kaum mit elo"
