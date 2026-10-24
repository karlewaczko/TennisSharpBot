"""The weekly player table: Tennis Abstract Elo + yElo joined onto the
last-52-week statistics, the dated Elo history, and the refresh wrapper."""
import datetime as dt
import json

import pandas as pd
import pytest

from tennissharp import player_data as pdx, player_stats as ps
from tennissharp.data import tennisabstract as ta, tennismylife as tml


def _match(date, winner, loser, surface="Hard", tour="atp", w_rank=10, l_rank=60):
    return {"date": pd.Timestamp(date), "tournament": "T", "surface": surface, "tier": "250",
            "best_of": 3, "source_tour": tour, "winner": winner, "loser": loser,
            "winner_rank": w_rank, "loser_rank": l_rank,
            "winner_ace": 8, "winner_df": 2, "winner_svpt": 60, "winner_1stin": 40,
            "winner_1stwon": 30, "winner_2ndwon": 12, "winner_svgms": 10,
            "winner_bpsaved": 2, "winner_bpfaced": 3,
            "loser_ace": 3, "loser_df": 4, "loser_svpt": 70, "loser_1stin": 42,
            "loser_1stwon": 27, "loser_2ndwon": 12, "loser_svgms": 10,
            "loser_bpsaved": 4, "loser_bpfaced": 8}


def _matches():
    rows = [_match(f"2026-09-{d:02d}", "Jannik Sinner", "Felix Auger-Aliassime") for d in range(1, 6)]
    rows += [_match(f"2026-08-{d:02d}", "Jannik Sinner", "Some Qualifier", surface="Clay",
                    tour="challenger") for d in range(1, 3)]
    rows += [_match(f"2026-09-{d:02d}", "Iga Swiatek", "Coco Gauff", tour="wta") for d in range(1, 4)]
    return pd.DataFrame(rows)


def _ta_elo():
    return pd.DataFrame([
        {"elo_rank": 1, "player": "Jannik Sinner", "elo": 2300.0, "helo": 2250.0, "celo": 2200.0,
         "gelo": 2150.0, "peak_elo": 2350.0, "official_rank": 1, "age": 25.2, "tour": "atp",
         "ta_updated": "2026-10-19"},
        {"elo_rank": 2, "player": "Felix Auger Aliassime", "elo": 1950.0, "tour": "atp",
         "ta_updated": "2026-10-19"},
        {"elo_rank": 3, "player": "Rated Only", "elo": 1800.0, "tour": "atp", "ta_updated": "2026-10-19"},
        {"elo_rank": 1, "player": "Iga Swiatek", "elo": 2100.0, "tour": "wta", "ta_updated": "2026-10-19"},
    ])


def _ta_yelo():
    return pd.DataFrame([
        {"yelo_rank": 1, "player": "Jannik Sinner", "yelo_wins": 44, "yelo_losses": 3, "yelo": 2323.0,
         "tour": "atp", "ta_updated": "2026-10-19"},
        {"yelo_rank": 9, "player": "Coco Gauff", "yelo_wins": 47, "yelo_losses": 15, "yelo": 2135.3,
         "tour": "wta", "ta_updated": "2026-10-19"},
    ])


def test_name_key_folds_hyphens_and_accents():
    assert pdx.name_key("Felix Auger-Aliassime") == pdx.name_key("Felix Auger Aliassime")
    assert pdx.name_key("Iga Świątek") == "iga swiatek"


def test_profile_table_is_the_union_of_both_sources():
    book = ps.StatBook(_matches(), as_of="2026-10-20")
    table = pdx.build_profile_table(book, _ta_elo(), _ta_yelo())
    atp = table[table["tour"] == "atp"].set_index("player")
    wta = table[table["tour"] == "wta"].set_index("player")
    # Rated and active, rated only, active only -- all present.
    assert {"Jannik Sinner", "Felix Auger Aliassime", "Rated Only", "Some Qualifier"} <= set(atp.index)
    assert {"Iga Swiatek", "Coco Gauff"} <= set(wta.index)
    # Tennis Abstract's spelling wins where both have the player.
    assert "Felix Auger-Aliassime" not in atp.index
    sinner = atp.loc["Jannik Sinner"]
    assert sinner["elo"] == 2300.0 and sinner["yelo"] == 2323.0 and sinner["helo"] == 2250.0
    assert sinner["matches"] == 7 and sinner["wins"] == 7
    assert sinner["hard_matches"] == 5 and sinner["clay_matches"] == 2 and sinner["grass_matches"] == 0
    assert sinner["spw"] == pytest.approx(42 / 60, abs=1e-3)
    assert sinner["hold_pct"] == pytest.approx(0.9)
    assert sinner["dr"] == pytest.approx((31 / 70) / (1 - 42 / 60), abs=1e-3)
    assert pd.isna(sinner["grass_spw"])
    assert bool(sinner["in_ta_elo"]) and bool(sinner["in_ta_yelo"]) and bool(sinner["in_stats"])
    rated_only = atp.loc["Rated Only"]
    assert not rated_only["in_stats"] and rated_only["matches"] == 0 and pd.isna(rated_only["spw"])
    qual = atp.loc["Some Qualifier"]
    assert not qual["in_ta_elo"] and qual["matches"] == 2
    # Coco Gauff: yElo row and statistics, no Elo row in this fixture.
    gauff = wta.loc["Coco Gauff"]
    assert gauff["in_ta_yelo"] and gauff["in_stats"] and not gauff["in_ta_elo"]
    # Sorted by Elo rank within each tour, unrated players last.
    assert table[table["tour"] == "atp"]["player"].tolist()[:3] == [
        "Jannik Sinner", "Felix Auger Aliassime", "Rated Only"]


def test_profile_table_without_statistics_still_lists_the_rated_players():
    table = pdx.build_profile_table(None, _ta_elo(), _ta_yelo())
    assert set(table["player"]) == {"Jannik Sinner", "Felix Auger Aliassime", "Rated Only",
                                    "Iga Swiatek", "Coco Gauff"}
    assert (table["matches"] == 0).all()


def test_elo_history_appends_each_update_once(tmp_path):
    path = tmp_path / "hist.csv"
    assert pdx.append_elo_history(path, _ta_elo(), _ta_yelo()) == 5
    assert pdx.append_elo_history(path, _ta_elo(), _ta_yelo()) == 0      # same TA update
    newer = _ta_elo().assign(ta_updated="2026-10-26", elo=lambda d: d["elo"] + 5)
    assert pdx.append_elo_history(path, newer, None) == 4
    hist = pd.read_csv(path)
    assert sorted(hist["ta_updated"].unique()) == ["2026-10-19", "2026-10-26"]
    assert list(hist.columns) == pdx.HISTORY_COLUMNS


def test_elo_history_without_a_page_date_uses_today(tmp_path):
    path = tmp_path / "hist.csv"
    undated = _ta_elo().drop(columns=["ta_updated"])
    pdx.append_elo_history(path, undated, None, today=dt.date(2026, 10, 27))
    assert set(pd.read_csv(path)["ta_updated"]) == {"2026-10-27"}


def test_refresh_writes_every_output(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "fetch_all_elo_ratings", _ta_elo)
    monkeypatch.setattr(ta, "fetch_all_yelo_ratings", _ta_yelo)
    monkeypatch.setattr(tml, "load_all", lambda start_season=None, tours=None: _matches())
    meta = pdx.refresh(out_dir=tmp_path, today=dt.date(2026, 10, 20))
    assert meta["errors"] == []
    for name in ("player_profiles_atp.csv", "player_profiles_wta.csv", "player_profiles_meta.json",
                 "ta_elo_current.csv", "ta_elo_atp_general.csv", "ta_elo_wta_general.csv",
                 "ta_yelo_current.csv", "ta_elo_history.csv"):
        assert (tmp_path / name).exists(), name
    assert len(list(tmp_path.glob("ta_leaders_*.csv"))) == 50
    saved = json.loads((tmp_path / "player_profiles_meta.json").read_text())
    assert saved["ta_elo_last_update"] == {"atp": "2026-10-19", "wta": "2026-10-19"}
    assert saved["players"]["atp"]["with_elo_and_stats"] == 2
    assert saved["stats_last_match"]["wta"] == "2026-09-03"


def test_a_failed_elo_fetch_falls_back_and_adds_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "fetch_all_elo_ratings", _ta_elo)
    monkeypatch.setattr(ta, "fetch_all_yelo_ratings", _ta_yelo)
    monkeypatch.setattr(tml, "load_all", lambda start_season=None, tours=None: _matches())
    pdx.refresh(out_dir=tmp_path, today=dt.date(2026, 10, 20))
    rows_before = len(pd.read_csv(tmp_path / "ta_elo_history.csv"))

    def down():
        raise ConnectionError("Tennis Abstract offline")

    monkeypatch.setattr(ta, "fetch_all_elo_ratings", down)
    meta = pdx.refresh(out_dir=tmp_path, today=dt.date(2026, 10, 27))
    assert any("Elo" in e for e in meta["errors"])
    # The table is still built, from the last saved ratings ...
    atp = pd.read_csv(tmp_path / "player_profiles_atp.csv")
    assert atp.loc[atp["player"] == "Jannik Sinner", "elo"].iloc[0] == 2300.0
    # ... but last week's ratings are not filed as a new snapshot.
    assert len(pd.read_csv(tmp_path / "ta_elo_history.csv")) == rows_before


def test_yelo_page_parses(tmp_path):
    from pathlib import Path
    html = (Path(__file__).parent / "fixtures" / "ta_yelo_sample.html").read_text(encoding="utf-8")
    df = ta.parse_yelo_html(html, "atp")
    assert df.iloc[0][["yelo_rank", "player", "yelo_wins", "yelo_losses", "yelo"]].tolist() == [
        1, "Jannik Sinner", 44, 3, 2323.0]
    assert (df["ta_updated"] == "2026-10-19").all()
    assert ta.parse_last_update("no date here") is None


@pytest.mark.parametrize("stats_name,ta_name", [
    ("Christopher O'Connell", "Christopher Oconnell"),
    ("Soonwoo Kwon", "Soon Woo Kwon"),
    ("Yunchaokete Bu", "Bu Yunchaokete"),
    ("Daniel Merida", "Daniel Merida Aguilar"),
    ("Jay Friend", "Jay Dylan Hara Friend"),
    ("Abdullah Shelbayh", "Abedallah Shelbayh"),
])
def test_different_spellings_of_one_player_are_reconciled(stats_name, ta_name):
    a, b = pdx.name_key(stats_name), pdx.name_key(ta_name)
    assert pdx.reconcile_keys({a}, {b}) == {a: b}


def test_reconciliation_refuses_ambiguous_pairs():
    # Two rated players both extend "Daniel Merida": neither is taken.
    stats = {pdx.name_key("Daniel Merida")}
    rated = {pdx.name_key("Daniel Merida Aguilar"), pdx.name_key("Daniel Merida Lopez")}
    assert pdx.reconcile_keys(stats, rated) == {}
    # Different people with a shared surname stay apart.
    assert pdx.reconcile_keys({pdx.name_key("Alex Hernandez")},
                              {pdx.name_key("Juan Alejandro Hernandez Serrano")}) == {}


def test_reconciled_players_share_one_row():
    m = pd.DataFrame([_match("2026-09-01", "Christopher O'Connell", "Yunchaokete Bu")])
    book = ps.StatBook(m, as_of="2026-10-20")
    elo = pd.DataFrame([
        {"elo_rank": 50, "player": "Christopher Oconnell", "elo": 1800.0, "tour": "atp", "ta_updated": "2026-10-19"},
        {"elo_rank": 60, "player": "Bu Yunchaokete", "elo": 1780.0, "tour": "atp", "ta_updated": "2026-10-19"},
    ])
    table = pdx.build_profile_table(book, elo, None)
    assert len(table) == 2
    assert table["in_stats"].all() and table["in_ta_elo"].all()
    assert set(table["player"]) == {"Christopher Oconnell", "Bu Yunchaokete"}
