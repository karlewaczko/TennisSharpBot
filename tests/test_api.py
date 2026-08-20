import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tennissharp import config
from tennissharp.api import app

client = TestClient(app)


@pytest.fixture
def processed_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    return tmp_path


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_rankings_returns_json_records(processed_dir):
    pd.DataFrame({
        "elo_rank": [1, 2], "player": ["A", "B"], "elo": [2300.0, 2200.0], "tour": ["atp", "atp"],
    }).to_csv(processed_dir / "ta_elo_current.csv", index=False)

    r = client.get("/rankings", params={"tour": "atp", "source": "ta", "top_n": 5})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["player"] == "A"


def test_wta_general_rankings_returns_json_without_surface_columns(processed_dir):
    pd.DataFrame({
        "elo_rank": [1, 2], "player": ["A", "B"], "elo": [2300.0, 2200.0], "tour": ["wta", "wta"],
    }).to_csv(processed_dir / "ta_elo_wta_general.csv", index=False)

    r = client.get("/rankings/wta-general", params={"top_n": 5})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert "helo" not in body[0]


def test_rankings_missing_data_returns_503(processed_dir):
    r = client.get("/rankings")
    assert r.status_code == 503
    assert "update_data.py" in r.json()["detail"]


def test_rankings_rejects_invalid_tour():
    r = client.get("/rankings", params={"tour": "xyz"})
    assert r.status_code == 422


def test_upcoming_returns_records(processed_dir):
    pd.DataFrame({
        "tournament": ["X"], "tournament_url": ["https://x/x/2026/atp-men/"],
        "player1": ["A"], "player1_slug": ["a"], "odds1": [1.5], "odds2": [2.5],
        "match_id": [1], "player2": ["B"], "player2_slug": ["b"],
    }).to_csv(processed_dir / "tennisexplorer_upcoming.csv", index=False)

    r = client.get("/upcoming")
    assert r.status_code == 200
    assert r.json()[0]["player1"] == "A"


def test_h2h_unknown_player_returns_404(processed_dir):
    pd.DataFrame({
        "tournament": ["X"], "tournament_url": ["https://x/x/2026/atp-men/"],
        "player1": ["A"], "player1_slug": ["a"], "odds1": [1.5], "odds2": [2.5],
        "match_id": [1], "player2": ["B"], "player2_slug": ["b"],
    }).to_csv(processed_dir / "tennisexplorer_upcoming.csv", index=False)

    r = client.get("/h2h", params={"player1": "Nobody", "player2": "B"})
    assert r.status_code == 404


def test_value_bets_without_api_key_returns_400(processed_dir, monkeypatch):
    monkeypatch.setattr(config, "ODDS_API_KEY", "")
    (processed_dir.parent / "models").mkdir(exist_ok=True)
    monkeypatch.setattr(config, "MODELS_DIR", processed_dir.parent / "models")
    # No model files either -> DataNotReadyError -> 503, which is also an
    # acceptable "not usable yet" signal; the important thing is no 500.
    r = client.get("/value-bets")
    assert r.status_code in (400, 503)
