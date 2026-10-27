"""PolyInsider as a second source: money strings, the trader page's title
and embedded statistics, and a page that cannot be read."""
import json

import pytest
import requests

from tennissharp.data import polyinsider as pi


def _page(title, objects):
    chunk = json.dumps("8:" + json.dumps(objects, separators=(",", ":")))[1:-1]   # compact and escaped, like the real one
    return f"<html><head><title>{title}</title></head><body><script>self.__next_f.push([1,\"{chunk}\"])</script></body></html>"


PAGE = _page("Kyn008 Polymarket: +$75.7K P&amp;L, $5.5M Volume | PolyInsider", [
    {"range": "all", "points": [{"t": 1, "p": 0}]},                                   # the P&L chart, no stats
    {"range": "1m", "winRate": 61.2, "closedPredictions": 170, "winningPredictions": 104, "totalVolume": 1.6e6},
    {"range": "all", "winRate": 57.5, "closedPredictions": 1200, "winningPredictions": 690, "losingPredictions": 510,
     "totalVolume": 5.1e6, "totalTrades": 9000, "biggestWin": 41000.0},
])


def test_money_strings():
    assert pi.money("+$1.3M") == 1_300_000 and pi.money("-$99.5K") == -99_500 and pi.money("−$2B") == -2e9
    assert pi.money("$850") == 850 and pi.money("$1,234.5") == 1234.5 and pi.money("n/a") is None


def test_trader_page_figures():
    got = pi.parse_trader(PAGE)
    assert got["pnl"] == pytest.approx(75_700) and got["volume"] == pytest.approx(5_500_000)
    assert got["winRate"] == 57.5 and got["closedPredictions"] == 1200 and got["biggestWin"] == 41000.0
    assert got["winRate_1m"] == 61.2 and got["closedPredictions_1m"] == 170
    assert pi.parse_trader("<title>Something else</title>") is None


def test_an_unreadable_page_is_no_verdict():
    class Resp:
        def __init__(self, code, text=""): self.status_code, self.text = code, text

    class Http:
        def __init__(self, resp): self.resp, self.headers = resp, None
        def get(self, url, headers=None, timeout=None):
            self.headers = headers
            if isinstance(self.resp, Exception):
                raise self.resp
            return self.resp

    ok = Http(Resp(200, PAGE))
    assert pi.trader("0xabc", http=ok, sleep=lambda s: None)["pnl"] == pytest.approx(75_700)
    assert "TennisSharpBot" in ok.headers["User-Agent"]
    assert pi.trader("0xabc", http=Http(Resp(404)), sleep=lambda s: None) is None
    assert pi.trader("0xabc", http=Http(requests.ConnectionError("down")), sleep=lambda s: None) is None
    assert pi.market_url("nba-lal-por-2026-10-28") == "https://polyinsider.io/en/markets/nba-lal-por-2026-10-28"
