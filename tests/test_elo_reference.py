"""Ground-truth checks on the stored Tennis Abstract Elo tables.

The scrape reads an HTML table whose column order the site can change without
notice; a silent shift would mis-assign ratings across the whole file while
still producing a plausible-looking CSV. These values were transcribed from
the published leaderboards (last update 2026-08-10) and pin the ends and the
middle of each table, so a shifted or truncated parse fails loudly.

Skips rather than fails when the files are absent -- they are refreshed by
scripts/update_data.py and a clean checkout may not have run it yet.
"""
import pandas as pd
import pytest

from tennissharp import config

# (player, elo, helo, elo_rank) straight off the published tables.
WTA_REFERENCE = [
    ("Aryna Sabalenka", 2194.6, 2179.4, 1),
    ("Elena Rybakina", 2125.8, 2114.5, 2),
    ("Camila Osorio", 1795.7, 1766.9, 55),
    ("Ann Li", 1778.3, 1725.2, 67),
    ("Sara Lanca", 1019.6, 1003.5, 547),
]
ATP_REFERENCE = [
    ("Jannik Sinner", 2321.9, 2259.3, 1),
    ("Carlos Alcaraz", 2146.8, 2073.3, 2),
    ("Novak Djokovic", 1975.5, 1929.8, 7),
    ("Jan Kumstat", 1719.2, 1487.1, 100),
    ("Pierre Hugues Herbert", 1571.4, 1558.8, 197),
    ("Maximo Zeitune", 1043.6, 1131.8, 552),
]
EXPECTED_ROWS = {"wta": 547, "atp": 552}


def _load(tour: str) -> pd.DataFrame:
    path = config.PROCESSED_DIR / f"ta_elo_{tour}_general.csv"
    if not path.exists():
        pytest.skip(f"{path.name} fehlt -- scripts/update_data.py noch nicht gelaufen")
    return pd.read_csv(path)


@pytest.mark.parametrize("tour,reference", [("wta", WTA_REFERENCE), ("atp", ATP_REFERENCE)])
def test_ratings_match_the_published_table(tour, reference):
    df = _load(tour).set_index("player")
    for player, elo, helo, rank in reference:
        assert player in df.index, f"{player} fehlt in ta_elo_{tour}_general.csv"
        row = df.loc[player]
        assert row["elo"] == pytest.approx(elo, abs=0.05)
        assert row["helo"] == pytest.approx(helo, abs=0.05)
        assert int(row["elo_rank"]) == rank


@pytest.mark.parametrize("tour", ["wta", "atp"])
def test_table_is_complete_and_rank_ordered(tour):
    """A truncated scrape still parses; the row count and a contiguous rank
    sequence are what catch it."""
    df = _load(tour)
    assert len(df) == EXPECTED_ROWS[tour]
    ranks = df["elo_rank"].dropna().astype(int).tolist()
    assert ranks == sorted(ranks)
    assert ranks[0] == 1 and ranks[-1] == EXPECTED_ROWS[tour]


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
