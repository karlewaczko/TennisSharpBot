"""The live page of the ranked Polymarket wallets: whom it watches, which
sport an event belongs to, and that the embedded data cannot break out of
its script block."""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

from tennissharp import config

SCRIPTS = Path(__file__).parent.parent / "scripts"


@pytest.fixture(scope="module")
def live():
    spec = importlib.util.spec_from_file_location("build_pros_live", SCRIPTS / "build_pros_live.py")
    sys.path.insert(0, str(SCRIPTS))
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(SCRIPTS))


def _ranking(path, rows):
    pd.DataFrame([{"rank": i + 1, "name": n, "wallet": w, "pre_markets": 30, "stake": 5000.0, "pnl": 100.0,
                   "roi": 0.02, "clv_mean": 0.012, "clv_t": 4.2 - i} for i, (n, w) in enumerate(rows)]).to_csv(path, index=False)


def test_every_watched_account_gets_its_clv_in_each_sport(live, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(live, "STATS_DIR", tmp_path / "raw")
    monkeypatch.setattr(live, "WATCHED", tmp_path / "pm_watched_clv.csv")
    _ranking(tmp_path / "pm_tennis_traders.csv", [("Ace", "0xa"), ("Both", "0xb"), ("Deep", "0xd")])
    _ranking(tmp_path / "pm_basketball_traders.csv", [("Both", "0xb"), ("", "0xc")])
    (tmp_path / "pm_basketball_traders.json").write_text(json.dumps({"measured_at": "2026-10-26T00:00:00+00:00"}))
    (tmp_path / "raw").mkdir()
    pd.DataFrame([{"wallet": "0xc", "pre_markets": 14, "stake": 900.0, "pnl": -20.0, "clv_mean": -0.003, "clv_t": -0.4}]
                 ).to_csv(tmp_path / "raw" / "pm_tennis_wallet_stats.csv", index=False)
    data = live.collect(top_n=2)
    assert set(data["sports"]) == {"tennis", "basketball"}               # no football ranking yet
    by = {w["wallet"]: w for w in data["wallets"]}
    assert set(by) == {"0xa", "0xb", "0xc"}                             # 0xd ranks third: not watched
    assert by["0xb"]["ranks"] == {"tennis": 2, "basketball": 1}
    none = {"fees": None, "taker": None, "sig": None, "elite": None}    # a table from before fees were counted
    assert by["0xb"]["clv"]["tennis"] == {"rank": 2, "clv": 0.012, "gross": 0.012, "t": 3.2, "matches": 30,
                                          "stake": 5000, "pnl": 100, **none}
    assert by["0xc"]["clv"]["tennis"] == {"rank": None, "clv": -0.003, "gross": -0.003, "t": -0.4, "matches": 14,
                                          "stake": 900, "pnl": -20, **none}
    assert "basketball" not in by["0xa"]["clv"]                          # too few basketball matches
    live.write_watched(data)
    (tmp_path / "raw" / "pm_tennis_wallet_stats.csv").unlink()          # a rebuild without this run's tables
    again = {w["wallet"]: w for w in live.collect(top_n=2)["wallets"]}
    assert again["0xc"]["clv"]["tennis"] == by["0xc"]["clv"]["tennis"]  # falls back to what the page showed


def test_league_codes_map_to_their_sport(live):
    class Resp:
        def __init__(self, data): self._d = data
        def json(self): return self._d

    class Http:
        def get(self, url, timeout=None):
            return Resp([{"sport": "epl", "tags": "1,82,306,100639,100350"},
                         {"sport": "bkcba", "tags": "1,100639,28,103097"},
                         {"sport": "nba", "tags": "1,745,100639"},
                         {"sport": "wta", "tags": "1,864,100639,102123"},
                         {"sport": "nfl", "tags": "1,450,100639"},
                         {"sport": "nhl", "tags": "1,899,100639"}])

    got = live.sport_prefixes(Http())
    assert (got["epl"], got["bkcba"], got["nba"], got["wta"]) == ("soccer", "basketball", "basketball", "tennis")
    assert got["nfl"] == "football" and "nhl" not in got                # ice hockey is not covered

    class Down:
        def get(self, url, timeout=None):
            raise live.requests.ConnectionError("offline")

    assert live.sport_prefixes(Down())["atp"] == "tennis"               # the fallback still covers the big leagues


def test_embedded_data_cannot_close_the_script_block(live):
    template = (SCRIPTS / "templates" / "profis.html").read_text()
    page = live.render({"wallets": [{"wallet": "0xa", "name": "</script><script>alert(1)</script>", "ranks": {}}],
                        "sports": {}, "prefixes": {}, "top_n": 12}, template)
    block = re.search(r'<script id="pros-data" type="application/json">(.*?)</script>', page, re.S).group(1)
    assert json.loads(block.replace("<\\/", "</"))["wallets"][0]["name"].startswith("</script>")
    assert "alert(1)</script>" not in block
    with pytest.raises(AssertionError):
        live.render({}, "no placeholder here")


def test_only_edges_beyond_luck_are_watched_and_counted_after_fees(live, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(live, "STATS_DIR", tmp_path / "raw")
    monkeypatch.setattr(live, "WATCHED", tmp_path / "pm_watched_clv.csv")
    _ranking(tmp_path / "pm_tennis_traders.csv", [("Real", "0xr"), ("Luck", "0xl")])
    lb = pd.read_csv(tmp_path / "pm_tennis_traders.csv").assign(
        significant=[True, False], clv_net_mean=[0.008, 0.001], clv_net_t=[3.9, 0.4], fees=[120.0, 80.0],
        taker_share=[0.25, 1.0])
    lb.to_csv(tmp_path / "pm_tennis_traders.csv", index=False)
    data = live.collect(top_n=5)
    assert [w["wallet"] for w in data["wallets"]] == ["0xr"] and data["sports"]["tennis"]["significant"] == 1
    fig = data["wallets"][0]["clv"]["tennis"]
    assert (fig["clv"], fig["gross"], fig["t"], fig["fees"], fig["taker"], fig["sig"]) == (0.008, 0.012, 3.9, 120, 0.25, True)


def test_all_time_profit_comes_from_polymarket(live):
    class Resp:
        status_code = 200
        def __init__(self, data): self._d = data
        def json(self): return self._d
        def raise_for_status(self): pass

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            assert url.endswith("/v1/leaderboard") and params["timePeriod"] == "ALL"
            return Resp([{"pnl": -1969623.78, "vol": 69436312.9}] if params["user"] == "0xa" else [])

    wallets = [{"wallet": "0xa"}, {"wallet": "0xb"}]
    live.alltime(wallets, Http())
    assert wallets[0]["alltime"] == {"pnl": -1969624, "vol": 69436313} and "alltime" not in wallets[1]


def test_each_watched_account_gets_polyinsiders_view(live):
    wallets = [{"wallet": "0xa"}, {"wallet": "0xb"}]
    figures = {"0xa": {"pnl": 75700.0, "volume": 5.5e6, "winRate": 57.5, "closedPredictions": 1200,
                       "winningPredictions": 690, "winRate_1m": 61.2, "closedPredictions_1m": 170}}
    live.second_opinion(wallets, fetch=figures.get)
    assert wallets[0]["pi"] == {"pnl": 75700.0, "volume": 5.5e6, "win_rate": 57.5, "closed": 1200, "won": 690,
                                "win_rate_1m": 61.2, "closed_1m": 170}
    assert "pi" not in wallets[1]
