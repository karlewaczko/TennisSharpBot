import pandas as pd
import pytest

from tennissharp import config, service


@pytest.fixture
def processed_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    return tmp_path


def test_get_rankings_missing_file_raises_data_not_ready(processed_dir):
    with pytest.raises(service.DataNotReadyError):
        service.get_rankings(tour="atp", source="ta")


def test_get_rankings_ta_filters_by_tour(processed_dir):
    pd.DataFrame({
        "elo_rank": [1, 2, 1],
        "player": ["Alice Atp", "Bob Atp", "Carla Wta"],
        "elo": [2200, 2100, 2000],
        "tour": ["atp", "atp", "wta"],
    }).to_csv(processed_dir / "ta_elo_current.csv", index=False)

    atp = service.get_rankings(tour="atp", source="ta", top_n=10)
    assert list(atp["player"]) == ["Alice Atp", "Bob Atp"]

    wta = service.get_rankings(tour="wta", source="ta", top_n=10)
    assert list(wta["player"]) == ["Carla Wta"]


def test_get_wta_general_rankings_missing_file_raises_data_not_ready(processed_dir):
    with pytest.raises(service.DataNotReadyError):
        service.get_wta_general_rankings()


def test_get_wta_general_rankings_returns_ranked_general_elo(processed_dir):
    pd.DataFrame({
        "elo_rank": [2, 1, 3],
        "player": ["Bob", "Alice", "Carla"],
        "elo": [2100, 2200, 2000],
        "peak_elo": [2150, 2250, 2050],
        "tour": ["wta", "wta", "wta"],
    }).to_csv(processed_dir / "ta_elo_wta_general.csv", index=False)

    df = service.get_wta_general_rankings(top_n=2)
    assert len(df) == 2
    assert list(df["player"]) == ["Alice", "Bob"]  # sorted by elo_rank


def test_get_atp_general_rankings_missing_file_raises_data_not_ready(processed_dir):
    with pytest.raises(service.DataNotReadyError):
        service.get_atp_general_rankings()


def test_get_atp_general_rankings_returns_ranked_general_elo(processed_dir):
    pd.DataFrame({
        "elo_rank": [2, 1, 3],
        "player": ["Bob", "Alice", "Carla"],
        "elo": [2100, 2200, 2000],
        "helo": [2050, 2150, 1950],
        "celo": [2000, 2100, 1900],
        "gelo": [1950, 2050, 1850],
        "tour": ["atp", "atp", "atp"],
    }).to_csv(processed_dir / "ta_elo_atp_general.csv", index=False)

    df = service.get_atp_general_rankings(top_n=2)
    assert len(df) == 2
    assert list(df["player"]) == ["Alice", "Bob"]  # sorted by elo_rank
    for col in ("helo", "celo", "gelo"):
        assert col in df.columns


def test_get_tour_general_rankings_dispatches_by_tour(processed_dir):
    pd.DataFrame({"elo_rank": [1], "player": ["X"], "elo": [2000], "tour": ["atp"]},
                 ).to_csv(processed_dir / "ta_elo_atp_general.csv", index=False)
    pd.DataFrame({"elo_rank": [1], "player": ["Y"], "elo": [2000], "tour": ["wta"]},
                 ).to_csv(processed_dir / "ta_elo_wta_general.csv", index=False)

    assert service.get_tour_general_rankings("atp").iloc[0]["player"] == "X"
    assert service.get_tour_general_rankings("wta").iloc[0]["player"] == "Y"
    # Case-insensitive, matching get_rankings()'s convention.
    assert service.get_tour_general_rankings("ATP").iloc[0]["player"] == "X"


def test_get_rankings_own_ignores_tour_and_filters_low_sample(processed_dir):
    pd.DataFrame({
        "player": ["A", "B", "C"],
        "elo_overall": [2200, 2100, 2000],
        "matches_played": [50, 3, 100],  # B has too few matches to be trustworthy
    }).to_csv(processed_dir / "elo_ratings_current.csv", index=False)

    df = service.get_rankings(tour="atp", source="own", top_n=10)
    assert list(df["player"]) == ["A", "C"]


def test_get_surface_speed_by_tournament_name(processed_dir):
    pd.DataFrame({
        "date": ["2024-01-01", "2023-01-01", "2024-06-01"],
        "tournament": ["ATP Montpellier", "Montpellier", "Miami Masters"],
        "surface": ["Hard", "Hard", "Hard"],
        "ace_pct": [0.1, 0.12, 0.09],
        "surface_speed": [1.2, 1.1, 0.95],
    }).to_csv(processed_dir / "ta_surface_speed_history.csv", index=False)

    df = service.get_surface_speed(tournament="Montpellier")
    assert len(df) == 2  # both editions match despite the "ATP " prefix difference
    assert df.iloc[0]["date"].year == 2024  # most recent first


def test_get_surface_speed_default_uses_latest_season(processed_dir):
    pd.DataFrame({
        "date": ["2023-01-01", "2024-01-01", "2024-06-01"],
        "tournament": ["Old Event", "Fast 2024", "Slow 2024"],
        "surface": ["Hard", "Hard", "Clay"],
        "ace_pct": [0.1, 0.2, 0.05],
        "surface_speed": [1.0, 1.5, 0.6],
    }).to_csv(processed_dir / "ta_surface_speed_history.csv", index=False)

    df = service.get_surface_speed()
    assert set(df["tournament"]) == {"Fast 2024", "Slow 2024"}
    assert df.iloc[0]["tournament"] == "Fast 2024"  # sorted fastest-first


def test_get_upcoming_matches_filters_by_tour_url_suffix(processed_dir):
    pd.DataFrame({
        "tournament": ["Wimbledon", "Wimbledon"],
        "tournament_url": ["https://x/wimbledon/2026/atp-men/", "https://x/wimbledon/2026/wta-women/"],
        "player1": ["A", "C"], "player1_slug": ["a", "c"],
        "odds1": [1.5, 2.0], "odds2": [2.5, 1.8],
        "match_id": [1, 2],
        "player2": ["B", "D"], "player2_slug": ["b", "d"],
    }).to_csv(processed_dir / "tennisexplorer_upcoming.csv", index=False)

    atp = service.get_upcoming_matches(tour="atp")
    assert list(atp["player1"]) == ["A"]
    wta = service.get_upcoming_matches(tour="wta")
    assert list(wta["player1"]) == ["C"]


def test_find_player_slug_matches_either_side(processed_dir):
    pd.DataFrame({
        "tournament": ["X"], "tournament_url": ["https://x/x/2026/atp-men/"],
        "player1": ["Djokovic N."], "player1_slug": ["djokovic-abc"],
        "odds1": [1.2], "odds2": [4.0], "match_id": [1],
        "player2": ["Nadal R."], "player2_slug": ["nadal-def"],
    }).to_csv(processed_dir / "tennisexplorer_upcoming.csv", index=False)

    assert service.find_player_slug("djokovic") == ("Djokovic N.", "djokovic-abc")
    assert service.find_player_slug("Nadal") == ("Nadal R.", "nadal-def")
    assert service.find_player_slug("nobody") is None
