"""Polymarket tennis wallets: per-market profit, closing-line value, the
ranking, and the positions shown on the card."""
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tennissharp.data import polymarket_traders as pt

START = 1_000_000.0


def _t(wallet, side, outcome, size, price, ts, name=""):
    return {"proxyWallet": wallet, "side": side, "outcomeIndex": outcome, "size": size,
            "price": price, "timestamp": ts, "name": name}


def _market(slug, outcomes, prices, start="2026-10-23 15:00:00+00", cid="0xabc", volume=1000,
            question="Lyon Open: Taylor Fritz vs Daniel Altmaier", group=None):
    return {"conditionId": cid, "question": question, "groupItemTitle": group, "events": [{"slug": slug}],
            "outcomes": json.dumps(outcomes), "outcomePrices": json.dumps(prices),
            "gameStartTime": start, "volumeNum": volume, "sportsMarketType": "moneyline"}


def test_market_row_reads_the_winner_and_skips_voids_outrights_and_doubles():
    m = _market("atp-fritz-altmaie-2026-10-23", ["Taylor Fritz", "Daniel Altmaier"], ["1", "0"])
    row = pt.market_row(m)
    assert row["winner"] == 0 and row["tour"] == "atp" and row["tournament"] == "Lyon Open"
    assert pt.market_row(_market("atp-fritz-altmaie-2026-10-23", ["A", "B"], ["0.5", "0.5"])) is None
    assert pt.market_row(_market("atp-doubles-ab-cd-2026-10-23", ["A", "B"], ["1", "0"])) is None
    assert pt.market_row(_market("atp-tournament-winner-2026-135005", ["Yes", "No"], ["1", "0"])) is None
    draw = _market("epl-ars-che-2026-10-18", ["Yes", "No"], ["0", "1"], question="Will it be a draw?",
                   group="Draw (Arsenal vs. Chelsea)")
    assert pt.market_row(draw) is None                                   # not tennis
    row = pt.market_row(draw, "soccer")
    assert row["winner"] == 1 and row["tour"] == "epl" and row["label"].startswith("Draw")
    assert row["tournament"] == ""


class _Resp:
    status_code = 200

    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


def test_closed_markets_walks_creation_windows_and_tags():
    now = 1_800_000_000.0
    asked = []

    def when(ts):
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            asked.append(params)
            return _Resp([_market("atp-a-b-2027-01-15", ["A", "B"], ["0", "1"], when(now - 3600), "0x1", 5000),
                          _market("itf-a-b-2027-01-15", ["A", "B"], ["0", "1"], when(now - 3600), "0x2", 5000),
                          _market("wta-c-d-2026-12-06", ["C", "D"], ["0", "1"], when(now - 40 * 86400), "0x3", 5000),
                          _market("nba-mia-cha-2027-01-15", ["Heat", "Hornets"], ["0", "1"], when(now - 3600), "0x4", 5000)])

    got = pt.closed_markets(days=2, http=Http(), sleep=lambda s: None, now=now, ahead_days=3)
    assert [r["condition_id"] for r in got] == ["0x1"]     # ITF, too old and other sports are dropped
    assert {a["tag_id"] for a in asked} == set(pt.SPORT_TAGS["tennis"])
    assert {a["sports_market_types"] for a in asked} == {"moneyline"}
    assert len(asked) == 5                                  # two days back, three ahead, a day at a time
    assert asked[0]["end_date_min"] == pt._iso(now - 2 * 86400)          # walked by end date, not listing date
    asked.clear()
    assert pt.closed_markets(days=2, http=Http(), sleep=lambda s: None, now=now, min_volume=10_000) == []
    assert asked[0]["volume_num_min"] == 10_000
    got = pt.closed_markets(days=2, sport="basketball", tours=None, http=Http(), sleep=lambda s: None, now=now)
    assert set(pt.SPORT_TAGS) >= {"football", "baseball"}
    assert [r["condition_id"] for r in got] == ["0x1", "0x2", "0x4"]   # once, though asked under every tag


def test_market_trades_fall_back_to_bigger_trades_when_a_market_is_too_busy():
    asked = []
    taker = {"transactionHash": "0xt", "proxyWallet": "0xW", "side": "BUY", "outcomeIndex": 0, "size": 5}

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            asked.append(params)
            if "filterAmount" not in params or params["filterAmount"] < 100:
                return _Resp([{"price": 0.5}] * pt.TRADE_PAGE)          # always a full page
            if params["takerOnly"] == "true":
                return _Resp([taker] if params["offset"] == 0 else [])
            return _Resp([{"price": 0.5}] * 1200 if params["offset"] == 0 else [])

    trades, floor, takers = pt.market_trades("0xbusy", http=Http(), sleep=lambda s: None)
    assert floor == 100 and len(trades) == 1200
    assert [a.get("filterAmount") for a in asked] == [None, None, 50, 50, 100, 100]
    assert asked[-1]["takerOnly"] == "true" and takers == {("0xt", "0xw", 0, "BUY", 5.0)}

    class Small:
        def get(self, url, params=None, headers=None, timeout=None):
            return _Resp([{"price": 0.5}] * 30)

    assert pt.market_trades("0xquiet", http=Small(), sleep=lambda s: None)[1] == 0.0


def test_taker_fees_come_off_profit_and_closing_line_value():
    trades = [{**_t("T", "BUY", 0, 100, 0.40, START - 3600), "transactionHash": "0x1"},   # the taker
              {**_t("M", "SELL", 0, 100, 0.40, START - 3600), "transactionHash": "0x1"},  # its maker
              _t("C", "BUY", 0, 10, 0.50, START - 60)]
    close, rows = pt.account_market(trades, winner=0, start_ts=START, fee_rate=0.05,
                                    takers={pt.taker_key(trades[0])})
    by = {r["wallet"]: r for r in rows}
    fee = 0.05 * 0.40 * 0.60                                            # per share
    assert by["T"]["fees"] == pytest.approx(100 * fee) and by["T"]["taker_stake"] == pytest.approx(40.0)
    assert by["T"]["pnl"] == pytest.approx(-40 + 100 - 100 * fee)
    assert by["T"]["clv"] == pytest.approx(0.10) and by["T"]["clv_net"] == pytest.approx(0.10 - fee)
    assert by["M"]["fees"] == 0 and by["M"]["clv_net"] == pytest.approx(by["M"]["clv"])
    free = pt.account_market(trades, winner=0, start_ts=START, fee_rate=0.0, takers={pt.taker_key(trades[0])})[1]
    assert free[0]["fees"] == 0                                          # a market without fees


def test_only_edges_beyond_luck_count_as_significant():
    t = pd.Series(list(np.linspace(-2.0, 2.5, 297)) + [6.0, 6.5, 7.0])
    flags = pt.significant(t, pd.Series([30] * 300))
    assert flags.sum() == 3 and flags.iloc[-3:].all()                   # 2.5 alone is luck among 300
    assert not pt.significant(pd.Series([1.0, 0.5]), pd.Series([30, 30])).any()


def test_a_football_match_counts_once_per_wallet():
    rows = [  # home Yes, draw No and away No: one opinion on the home side
        {"wallet": "W", "name": "", "slug": "epl-ars-che-2026-10-18", "pnl": 30.0, "stake": 100.0, "pre_stake": 100.0,
         "live_stake": 0.0, "clv": 0.02, "both_sides": False, "trades": 2, "directional": 1.0},
        {"wallet": "W", "name": "Wally", "slug": "epl-ars-che-2026-10-18", "pnl": 10.0, "stake": 300.0, "pre_stake": 200.0,
         "live_stake": 100.0, "clv": 0.05, "both_sides": True, "trades": 3, "directional": 0.5},
        {"wallet": "W", "name": "", "slug": "epl-ars-che-2026-10-18", "pnl": -5.0, "stake": 50.0, "pre_stake": 0.0,
         "live_stake": 50.0, "clv": None, "both_sides": False, "trades": 1, "directional": None},
        {"wallet": "V", "name": "", "slug": "epl-ars-che-2026-10-18", "pnl": 1.0, "stake": 10.0, "pre_stake": 10.0,
         "live_stake": 0.0, "clv": -0.01, "both_sides": False, "trades": 1, "directional": 1.0},
    ]
    ev = pt.by_event(pd.DataFrame(rows))
    w = ev.set_index("wallet").loc["W"]
    assert len(ev) == 2 and w["name"] == "Wally" and w["trades"] == 6 and bool(w["both_sides"])
    assert w["pnl"] == pytest.approx(35.0) and w["stake"] == pytest.approx(450.0)
    assert w["clv"] == pytest.approx((0.02 * 100 + 0.05 * 200) / 300)
    assert w["directional"] == pytest.approx((1.0 * 100 + 0.5 * 200) / 300)
    tennis = pd.DataFrame(rows[:1])
    assert pt.by_event(tennis) is tennis                    # one market a match: nothing to merge


def test_profit_and_closing_line_value_per_wallet():
    trades = [
        _t("A", "BUY", 0, 100, 0.40, START - 3600, "sharp"),     # bought at 40c
        _t("B", "SELL", 0, 100, 0.40, START - 3600),             # the other side of it
        _t("C", "BUY", 0, 10, 0.50, START - 60),                 # last fill before start: close 0.50
        _t("A", "BUY", 1, 20, 0.30, START + 600),                # in-play, does not count for CLV
    ]
    close, rows = pt.account_market(trades, winner=0, start_ts=START)
    by = {r["wallet"]: r for r in rows}
    assert close == pytest.approx(0.50)
    assert by["A"]["pnl"] == pytest.approx(-40 + 100 - 6)        # 20 shares of the loser at 30c
    assert by["A"]["clv"] == pytest.approx(0.10)
    assert by["A"]["live_stake"] == pytest.approx(6.0) and by["A"]["both_sides"]
    assert by["B"]["pnl"] == pytest.approx(40 - 100)
    assert by["B"]["clv"] == pytest.approx(-0.10)
    assert by["C"]["clv"] == pytest.approx(0.0)
    assert by["A"]["directional"] == pytest.approx(1.0)     # only the pre-match buy counts
    maker = [_t("M", "BUY", 0, 50, 0.48, START - 900), _t("M", "BUY", 1, 50, 0.48, START - 800)]
    assert pt.account_market(maker + trades, 0, START)[1][0]["directional"] == pytest.approx(0.0)


def test_closing_price_converts_the_other_outcome():
    trades = [_t("X", "BUY", 1, 5, 0.70, START - 10)]
    assert pt.closing_price(trades, START) == pytest.approx(0.30)
    assert pt.closing_price(trades, None) is None
    assert pt.closing_price([_t("X", "BUY", 0, 5, 0.7, START + 10)], START) is None


def test_leaderboard_needs_enough_markets_and_stake_and_ranks_by_t():
    rows = []
    for i in range(22):   # steady small edge
        rows.append({"wallet": "steady", "name": "Steady", "pnl": 50, "stake": 500, "pre_stake": 500,
                     "live_stake": 0, "clv": 0.02 + 0.001 * (i % 3), "both_sides": False, "slug": f"m{i}",
                     "directional": 1.0})
        rows.append({"wallet": "maker", "name": "Maker", "pnl": 10, "stake": 900, "pre_stake": 900,
                     "live_stake": 0, "clv": 0.010 + 0.0001 * (i % 2), "both_sides": True,
                     "slug": f"m{i}", "directional": 0.1})
    for i in range(22):   # big but noisy
        rows.append({"wallet": "noisy", "name": "Noisy", "pnl": 400 if i % 2 else -300, "stake": 2000,
                     "pre_stake": 2000, "live_stake": 0, "clv": 0.10 if i % 2 else -0.08,
                     "both_sides": True, "slug": f"m{i}", "directional": 0.8})
    for i in range(3):    # too few markets
        rows.append({"wallet": "lucky", "name": "Lucky", "pnl": 5000, "stake": 5000, "pre_stake": 5000,
                     "live_stake": 0, "clv": 0.3, "both_sides": False, "slug": f"m{i}",
                     "directional": 1.0})
    lb = pt.leaderboard(pd.DataFrame(rows))
    assert lb["wallet"].tolist() == ["steady", "noisy"]
    assert lb.iloc[0]["rank"] == 1 and lb.iloc[0]["clv_t"] > lb.iloc[1]["clv_t"]
    assert lb.iloc[1]["two_sided_share"] == 1.0
    assert pt.leaderboard(pd.DataFrame()).empty
    assert "maker" in pt.leaderboard(pd.DataFrame(rows), min_directional=0)["wallet"].tolist()
    every = pt.wallet_table(pd.DataFrame(rows))                         # the unfiltered figures behind it
    assert set(every["wallet"]) == {"steady", "noisy", "maker", "lucky"} and "rank" not in every
    assert lb["significant"].tolist() == [True, False]                 # noisy's edge is within luck


def test_skill_persistence_and_market_structure():
    rows, markets = [], []
    for k in range(24):
        markets.append({"slug": f"m{k}", "start_ts": START + k * 3600})
    for w in range(30):
        skill = (w - 15) / 1000
        for k in range(24):
            rows.append({"wallet": f"w{w}", "slug": f"m{k}", "clv": skill + (0.001 if k % 2 else -0.001),
                         "stake": 100.0, "pre_stake": 100.0 if w else 10.0, "live_stake": 0.0 if w else 90.0})
    per, mk = pd.DataFrame(rows), pd.DataFrame(markets)
    got = pt.persistence(per, mk)
    assert got["wallets"] == 30 and got["corr"] > 0.99
    assert got["top_decile_next"] > got["all_next"] > got["bottom_decile_next"]
    assert pt.persistence(per[per.wallet == "w1"], mk) == {"wallets": 1}
    three_way = pd.concat([mk, mk, mk])                     # a football match lists its start three times
    assert pt.persistence(per, three_way) == got
    ms = pt.market_structure(per)
    assert ms["stake_usd"] == 72_000 and ms["in_play_share"] == round(90 * 24 / 72_000, 3)


def test_calibration_reports_brier_and_bins():
    mk = pd.DataFrame({"close_a": [0.8, 0.7, 0.3, 0.6], "winner": [0, 0, 1, 1]})
    cal = pt.calibration(mk)
    assert cal["n"] == 4
    assert cal["brier"] == pytest.approx(((0.2) ** 2 + 0.3 ** 2 + 0.3 ** 2 + 0.6 ** 2) / 4, abs=1e-4)
    assert cal["favourite_won"] == 0.75
    assert pt.calibration(pd.DataFrame({"close_a": [None], "winner": [0]}))["n"] == 0


def test_positions_keep_open_singles_only():
    class Resp:
        status_code = 200
        def __init__(self, data): self._d = data
        def json(self): return self._d
        def raise_for_status(self): pass

    data = [
        {"eventSlug": "atp-fritz-altmaie-2026-10-23", "outcome": "Taylor Fritz", "avgPrice": 0.7,
         "curPrice": 0.75, "size": 100, "initialValue": 70, "currentValue": 75, "redeemable": False},
        {"eventSlug": "atp-doubles-ab-cd-2026-10-23", "curPrice": 0.5, "size": 10},
        {"eventSlug": "nba-lakers", "curPrice": 0.5, "size": 10},
        {"eventSlug": "atp-tournament-winner-2026-135011", "curPrice": 0.3, "size": 10},
        {"eventSlug": "wta-a-b-2026-10-20", "curPrice": 1.0, "size": 10, "redeemable": True},
    ]

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            return Resp(data)

    got = pt.positions("0xW", http=Http(), sleep=lambda s: None)
    assert [p["slug"] for p in got] == ["atp-fritz-altmaie-2026-10-23"]
    assert got[0]["avg_price"] == 0.7


@pytest.fixture(scope="module")
def bd():
    scripts = Path(__file__).parent.parent / "scripts"
    spec = importlib.util.spec_from_file_location("build_dashboard", scripts / "build_dashboard.py")
    sys.path.insert(0, str(scripts))
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(scripts))


def test_pro_positions_land_on_the_card_with_the_fair_value(bd, tmp_path, monkeypatch):
    from tennissharp import config
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    pd.DataFrame([{"rank": 1, "name": "Pro", "wallet": "0xW", "markets": 20, "pre_markets": 15,
                   "stake": 9000, "pnl": 800, "roi": 0.09, "clv_mean": 0.03, "clv_t": 3.1,
                   "win_share": 0.6, "live_share": 0.1, "two_sided_share": 0.2}]
                 ).to_csv(tmp_path / "pm_tennis_traders.csv", index=False)
    board = [{"match_id": "7", "date": "2026-10-23", "tournament": "Lyon", "players": ["Fritz T.", "Altmaier D."],
              "fair": [0.78, 0.22], "fair_source": "Pinnacle", "fair_quality": "sharp", "ref_book": "Pinnacle",
              "books": {"Pinnacle": [1.25, 4.3], "bet365": [1.22, 4.5], "TennisExplorer": [1.3, 4.9]},
              "prediction_markets": [{"venue": "Polymarket",
                                      "url": "https://polymarket.com/event/atp-fritz-altmaie-2026-10-23"}]}]
    held = [{"wallet": "0xW", "slug": "atp-fritz-altmaie-2026-10-23", "title": "Lyon", "outcome": "Daniel Altmaier",
             "avg_price": 0.2, "cur_price": 0.24, "size": 500, "initial_value": 100, "current_value": 120}]
    out = bd.pro_positions(board, fetch=lambda w: held)
    p = out["positions"][0]
    assert p["side"] == "Altmaier D." and p["fair"] == 0.22
    assert p["best_book"] == "bet365" and p["best_odds"] == 4.5    # the anonymous schedule quote is left out
    assert p["ev_best"] == pytest.approx(0.22 * 4.5 - 1, abs=1e-4)
    assert out["leaderboard"][0]["name"] == "Pro"
    rows = bd.gap_rows([{**board[0], "circuit": "Tour",
                         "prediction_markets": [{"venue": "Kalshi", "mid": [0.77, 0.23], "ask": [0.78, 0.24],
                                                 "bid": [0.76, 0.22], "liquidity": 9000}]}], "t")
    assert len(rows) == 2 and rows[0]["spread"] == pytest.approx(0.02)


def test_no_ranking_yet_is_said_plainly(bd, tmp_path, monkeypatch):
    from tennissharp import config
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    assert bd.pro_positions([])["note"] == "noch keine Rangliste"


def test_consistency_needs_an_edge_in_both_halves():
    markets = pd.DataFrame({"slug": [f"m{k}" for k in range(20)], "start_ts": [START + k * 3600 for k in range(20)]})
    rows = []
    for k in range(20):
        rows.append({"wallet": "both", "slug": f"m{k}", "clv": 0.02, "clv_net": 0.01})
        rows.append({"wallet": "early", "slug": f"m{k}", "clv": 0.02, "clv_net": 0.03 if k < 10 else -0.01})
    h = pt.halves(pd.DataFrame(rows), markets)
    assert h.loc["both", "clv_net_first"] > 0 and h.loc["both", "clv_net_second"] > 0
    assert h.loc["early", "clv_net_second"] < 0 and h.loc["early", "matches_first"] == 10


def test_the_elite_meets_every_criterion():
    lb = pd.DataFrame([
        {"wallet": "0xA", "significant": True, "consistent": True, "pnl": 500.0},    # all good, ahead all-time
        {"wallet": "0xB", "significant": True, "consistent": True, "pnl": 300.0},    # loses all-time
        {"wallet": "0xC", "significant": True, "consistent": False, "pnl": 900.0},   # one good half only
        {"wallet": "0xD", "significant": False, "consistent": True, "pnl": 100.0},   # within luck
        {"wallet": "0xE", "significant": True, "consistent": True, "pnl": -50.0},    # lost money in the window
    ])
    asked = []

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            asked.append(params["user"])
            return _Resp([{"pnl": 25000.0 if params["user"] == "0xA" else -1969623.0, "vol": 1e6}])

    out = pt.mark_elite(lb, http=Http(), sleep=lambda s: None)
    assert out["elite"].tolist() == [True, False, False, False, False]
    assert asked == ["0xA", "0xB"]                                   # all-time looked up only where the rest holds
    assert out.loc[1, "alltime_pnl"] == -1969623.0


def test_a_second_source_in_the_red_rules_a_wallet_out():
    lb = pd.DataFrame([{"wallet": w, "significant": True, "consistent": True, "pnl": 500.0} for w in ("0xA", "0xB", "0xC")])

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            return _Resp([{"pnl": 10000.0, "vol": 1e6}])                    # all three ahead on Polymarket

    opinions = {"0xA": {"pnl": 75700.0, "winRate": 57.5, "closedPredictions": 1200},
                "0xB": {"pnl": -99504.6, "winRate": 50.4, "closedPredictions": 24749}}
    out = pt.mark_elite(lb, http=Http(), sleep=lambda s: None, second_opinion=opinions.get)
    assert out["elite"].tolist() == [True, False, True]                      # 0xC: page unreadable, no verdict
    assert out.loc[0, "pi_win_rate"] == 57.5 and out.loc[1, "pi_pnl"] == -99504.6
