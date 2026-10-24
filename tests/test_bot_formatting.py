import pandas as pd

from tennissharp.bot import formatting


def test_format_rankings_ta_source():
    df = pd.DataFrame({"player": ["Sinner J.", "Alcaraz C."], "elo": [2330.0, 2150.0]})
    text = formatting.format_rankings(df, "atp", "ta")
    assert "ATP" in text
    assert "1. Sinner J. — 2330" in text
    assert "2. Alcaraz C. — 2150" in text


def test_format_rankings_own_source_notes_no_tour_split():
    df = pd.DataFrame({"player": ["Sinner J."], "elo_overall": [2340.0]})
    text = formatting.format_rankings(df, "atp", "own")
    assert "trennt Touren aktuell nicht" in text


def test_format_rankings_empty():
    text = formatting.format_rankings(pd.DataFrame(), "atp", "ta")
    assert "Keine Elo-Daten" in text


def test_format_rankings_escapes_html():
    df = pd.DataFrame({"player": ["<script>alert(1)</script>"], "elo": [2000.0]})
    text = formatting.format_rankings(df, "atp", "ta")
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_format_surface_speed_with_tournament():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01"]),
        "tournament": ["Montpellier"], "surface": ["Hard"],
        "ace_pct": [0.15], "surface_speed": [1.2],
    })
    text = formatting.format_surface_speed(df, "Montpellier")
    assert "Montpellier" in text
    assert "1.20" in text
    assert "15.0%" in text


def test_format_surface_speed_empty_mentions_query():
    text = formatting.format_surface_speed(pd.DataFrame(), "Nonexistent Cup")
    assert "Nonexistent Cup" in text


def test_format_upcoming_with_and_without_odds():
    df = pd.DataFrame({
        "tournament": ["Wimbledon", "Wimbledon"],
        "player1": ["A", "C"], "player2": ["B", "D"],
        "odds1": [1.5, float("nan")], "odds2": [2.5, float("nan")],
    })
    text = formatting.format_upcoming(df, "atp")
    assert "Quote 1.50 / 2.50" in text
    assert "C vs D" in text and "Quote" not in text.split("C vs D")[1].split("\n")[0]


def test_format_h2h_basic():
    history = pd.DataFrame({
        "year": [2026, 2026], "tournament": ["Wimbledon", "Wimbledon"],
        "player": ["Sinner J.", "Zverev A."], "sets_won": [3, 1], "round": ["F", "F"],
    })
    result = {"player1": "Sinner J.", "player2": "Zverev A.", "wins1": 5, "wins2": 1, "history": history}
    text = formatting.format_h2h(result)
    assert "5 : 1" in text
    assert "Sinner J. d. Zverev A." in text


def test_format_value_bets_empty():
    text = formatting.format_value_bets(pd.DataFrame())
    assert "Keine Value Bets" in text


def test_format_value_bets_includes_disclaimer():
    df = pd.DataFrame({
        "player": ["A"], "opponent": ["B"], "bookmaker": ["Pinnacle"],
        "odds": [2.1], "model_prob": [0.55], "market_fair_prob": [0.48],
        "edge": [0.07], "suggested_stake": [42.0],
    })
    text = formatting.format_value_bets(df)
    assert "A vs B" in text
    assert formatting.DISCLAIMER in text
