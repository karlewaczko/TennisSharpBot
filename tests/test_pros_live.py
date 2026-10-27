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


def test_a_wallet_ranked_in_two_sports_is_watched_once(live, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
    _ranking(tmp_path / "pm_tennis_traders.csv", [("Ace", "0xa"), ("Both", "0xb")])
    _ranking(tmp_path / "pm_basketball_traders.csv", [("Both", "0xb"), ("", "0xc")])
    (tmp_path / "pm_basketball_traders.json").write_text(json.dumps({"measured_at": "2026-10-26T00:00:00+00:00"}))
    data = live.collect(top_n=2)
    assert set(data["sports"]) == {"tennis", "basketball"}               # no football ranking yet
    assert data["sports"]["basketball"]["measured_at"].startswith("2026-10-26")
    by = {w["wallet"]: w for w in data["wallets"]}
    assert len(by) == 3 and by["0xb"]["ranks"] == {"tennis": {"rank": 2, "clv": 0.012, "t": 3.2, "matches": 30,
                                                              "stake": 5000, "pnl": 100},
                                                   "basketball": {"rank": 1, "clv": 0.012, "t": 4.2, "matches": 30,
                                                                  "stake": 5000, "pnl": 100}}
    assert by["0xc"]["name"] == ""


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
                         {"sport": "nfl", "tags": "1,450,100639"}])

    got = live.sport_prefixes(Http())
    assert (got["epl"], got["bkcba"], got["nba"], got["wta"]) == ("soccer", "basketball", "basketball", "tennis")
    assert "nfl" not in got

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
