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


def _page(rows, cursor=None):
    """A Data API v2 answer: rows in `data`, the next page's cursor in `pagination`."""
    return _Resp({"data": rows, "pagination": {"next_cursor": cursor, "has_more": cursor is not None}})


def test_market_trades_fall_back_to_bigger_trades_when_a_market_is_too_busy():
    asked = []
    taker = {"transaction_hash": "0xt", "proxy_wallet": "0xW", "side": "BUY", "outcome_index": 0, "size": 5}

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            asked.append(params)
            assert url.endswith("/v2/trades") and params["condition"] == "0xbusy" and "market" not in params
            if "filter_amount" not in params or params["filter_amount"] < 100:
                return _page([{"price": 0.5}] * pt.TRADE_PAGE, cursor="more")    # never ends
            if params["taker_only"] == "true":
                return _page([taker])
            return _page([{"price": 0.5}] * 1200)

    trades, floor, takers = pt.market_trades("0xbusy", http=Http(), sleep=lambda s: None)
    pages = pt.MAX_FILLS // pt.TRADE_PAGE
    assert floor == 100 and len(trades) == 1200
    assert [a.get("filter_amount") for a in asked] == [None] * pages + [50] * pages + [100, 100]
    assert "limit" in asked[0] and "cursor" not in asked[0] and asked[1]["cursor"] == "more" and "limit" not in asked[1]
    assert asked[-1]["taker_only"] == "true" and takers == {("0xt", "0xw", 0, "BUY", 5.0)}

    class Small:
        def get(self, url, params=None, headers=None, timeout=None):
            return _page([{"price": 0.5, "proxy_wallet": "0xA", "outcome_index": 1}] * 30)

    trades, floor, _ = pt.market_trades("0xquiet", http=Small(), sleep=lambda s: None)
    assert floor == 0.0 and trades[0]["proxyWallet"] == "0xA" and trades[0]["outcomeIndex"] == 1


def test_track_record_follows_polyinsiders_method():
    import requests
    now = 1_800_000_000.0                                   # 15 Jan 2027: the last month starts 16 Dec
    stats = {"data": {"all_time_pnl": {"realized_pnl": 900.0, "unrealized_pnl": -100.0, "volume": 50000.0}}}
    closed = [{"condition_id": "0xa", "total_pnl": 50.0, "end_date": "2027-01-10"},     # won, this month
              {"condition_id": "0xb", "total_pnl": -20.0, "end_date": "2026-10-01"},
              {"condition_id": "0xc", "total_pnl": 30.0, "end_date": "2026-09-01"},     # one market, both outcomes:
              {"condition_id": "0xc", "total_pnl": -40.0, "end_date": "2026-09-01"}]    # lost on balance
    held = [{"condition_id": "0xd", "total_pnl": -10.0, "end_date": "2027-01-12"}]       # lost at resolution, still held
    asked = []

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            asked.append((url.rsplit("/", 1)[-1], params.get("status")))
            assert url.endswith("/user-stats") or params["sort_by"] == "TIMESTAMP"         # newest first, not by profit
            if url.endswith("/user-stats"):
                return _Resp(stats)
            return _page(closed if params["status"] == "CLOSED" else held)

    rec = pt.track_record("0xW", http=Http(), sleep=lambda s: None, now=now)
    assert (rec["closedPredictions"], rec["winningPredictions"], rec["winRate"]) == (4, 1, 25.0)
    assert (rec["closedPredictions_1m"], rec["winningPredictions_1m"], rec["winRate_1m"]) == (2, 1, 50.0)
    assert (rec["pnl"], rec["volume"], rec["complete"]) == (800.0, 50000.0, True)   # realised plus unrealised
    assert {("positions", "CLOSED"), ("positions", "REDEEMABLE")} <= set(asked)

    class Down:
        def get(self, url, params=None, headers=None, timeout=None):
            raise requests.ConnectionError("down")

    assert pt.track_record("0xW", http=Down(), sleep=lambda s: None) is None


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


def test_maker_fills_are_told_apart_with_or_without_a_fee():
    trades = [{**_t("T", "BUY", 0, 100, 0.40, START - 3600), "transactionHash": "0x1"},   # the taker
              {**_t("M", "SELL", 0, 100, 0.40, START - 3600), "transactionHash": "0x1"},  # its maker
              _t("C", "BUY", 0, 10, 0.50, START - 60)]
    takers = {pt.taker_key(trades[0])}
    by = {r["wallet"]: r for r in pt.account_market(trades, winner=0, start_ts=START, takers=takers)[1]}
    assert by["T"]["taker_stake"] == pytest.approx(40.0) and by["T"]["maker_pre"] == 0   # a taker, fee or not
    assert by["M"]["maker_pre"] == pytest.approx(60.0) and by["M"]["clv_maker"] == pytest.approx(-0.10)
    blind = {r["wallet"]: r for r in pt.account_market(trades, winner=0, start_ts=START)[1]}
    assert blind["M"]["maker_pre"] == 0 and blind["M"]["clv_maker"] is None   # no taker listing: nobody counts


def test_the_edge_counts_maker_fills_against_the_makers_average():
    pm = pd.DataFrame([
        {"wallet": "maker", "pre_stake": 100.0, "maker_pre": 100.0, "clv_maker": 0.010, "clv": 0.010, "clv_net": 0.010},
        {"wallet": "other", "pre_stake": 300.0, "maker_pre": 300.0, "clv_maker": 0.002, "clv": 0.002, "clv_net": 0.002},
        {"wallet": "taker", "pre_stake": 200.0, "maker_pre": 0.0, "clv_maker": None, "clv": 0.012, "clv_net": 0.010},
        {"wallet": "half", "pre_stake": 100.0, "maker_pre": 50.0, "clv_maker": 0.004, "clv": 0.008, "clv_net": 0.008},
    ])
    b = pt.maker_baseline(pm)
    assert b == pytest.approx((0.010 * 100 + 0.002 * 300 + 0.004 * 50) / 450)     # dollar-weighted: 0.4c
    e = pt.with_edge(pm).set_index("wallet")
    assert e.loc["maker", "clv_edge"] == pytest.approx(0.010 - b)
    assert e.loc["taker", "clv_edge"] == pytest.approx(0.010)            # it paid the spread: unchanged
    assert e.loc["half", "clv_edge"] == pytest.approx(0.008 - b / 2)
    assert pt.maker_baseline(pm.assign(clv_maker=-0.01)) == 0.0          # makers in the red: no bonus for making
    old = pd.DataFrame([{"wallet": "x", "pre_stake": 10.0, "clv": 0.01}])
    assert pt.with_edge(old)["clv_edge"].iloc[0] == pytest.approx(0.01)  # rows from before makers were counted


def test_a_maker_is_measured_against_the_other_makers_in_its_match():
    row = lambda w, slug, d, c: {"wallet": w, "slug": slug, "pre_stake": d, "maker_pre": d, "clv_maker": c,  # noqa: E731
                                 "clv": c, "clv_net": c}
    pm = pd.DataFrame([row("star", "thin", 1000.0, 0.030), row("a", "thin", 600.0, 0.020), row("b", "thin", 400.0, 0.025),
                       row("star", "deep", 1000.0, 0.004), row("c", "deep", 300.0, 0.002),     # too few others: sport's average
                       {"wallet": "taker", "slug": "thin", "pre_stake": 500.0, "maker_pre": 0.0, "clv_maker": None,
                        "clv": -0.01, "clv_net": -0.015}])
    e = pt.with_edge(pm).set_index(["wallet", "slug"])
    others = (0.020 * 600 + 0.025 * 400) / 1000                          # the star itself left out
    assert e.loc[("star", "thin"), "maker_base"] == pytest.approx(others)
    assert e.loc[("star", "thin"), "clv_edge"] == pytest.approx(0.030 - others)
    assert e.loc[("star", "deep"), "maker_base"] == pytest.approx(pt.maker_baseline(pm))
    assert e.loc[("taker", "thin"), "clv_edge"] == pytest.approx(-0.015)    # it paid the spread: unchanged
    summary = pt.maker_summary(pm)
    assert summary["maker_baseline"] == pytest.approx(pt.maker_baseline(pm), abs=1e-5)
    assert summary["maker_baseline_match_median"] > 0


def test_candidates_pass_a_looser_check_than_the_proven():
    t = pd.Series(list(np.linspace(-2.0, 2.0, 294)) + [3.0, 3.1, 3.2, 3.3, 6.0, 7.0])
    n = pd.Series([30] * 300)
    assert list(t[pt.significant(t, n)]) == [6.0, 7.0]
    assert list(t[pt.significant(t, n, pt.CANDIDATE_Q)]) == [3.0, 3.1, 3.2, 3.3, 6.0, 7.0]


def test_the_watch_list_holds_every_wallet_with_an_edge_in_profit():
    lb = pd.DataFrame({"wallet": ["0xa", "0xb", "0xc", "0xd", "0xe", "0xf"], "rank": range(1, 7),
                       "elite": [False, False, True, False, False, False],
                       "significant": [False, True, True, False, True, False],
                       "candidate": [True, False, False, False, False, True]})
    alltime = {"0xa": (1.0, 2.0), "0xb": (1.0, 2.0), "0xc": (1.0, 2.0), "0xd": (1.0, 2.0), "0xe": (-5.0, 9.0),
               "0xf": (1.0, 2.0)}
    # every criterion first, then the proven, then the candidates; 0xd has no edge, 0xe is in loss
    assert list(pt.watch_list(lb, alltime.get)["wallet"]) == ["0xc", "0xb", "0xa", "0xf"]
    assert list(pt.watch_list(lb, alltime.get, cap=2)["wallet"]) == ["0xc", "0xb"]
    assert pt.watch_list(lb.drop(columns=["elite", "significant", "candidate"]), alltime.get).empty


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
    makers = pd.DataFrame([{**r, "maker_pre": m, "clv_maker": c} for r, (m, c) in
                           zip(rows, [(100.0, 0.02), (50.0, 0.04), (0.0, None), (0.0, None)])])
    mk = pt.by_event(makers).set_index("wallet").loc["W"]
    assert mk["maker_pre"] == pytest.approx(150.0) and mk["clv_maker"] == pytest.approx((0.02 * 100 + 0.04 * 50) / 150)
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
        {"event_slug": "atp-fritz-altmaie-2026-10-23", "outcome": "Taylor Fritz", "avg_price": 0.7,
         "current_price": 0.75, "current_size": 100, "current_value": 75, "redeemable": False},
        {"event_slug": "atp-doubles-ab-cd-2026-10-23", "current_price": 0.5, "current_size": 10},
        {"event_slug": "nba-lakers", "current_price": 0.5, "current_size": 10},
        {"event_slug": "atp-tournament-winner-2026-135011", "current_price": 0.3, "current_size": 10},
        {"event_slug": "wta-a-b-2026-10-20", "current_price": 1.0, "current_size": 10, "redeemable": True},
    ]

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            assert url.endswith("/v2/positions") and params["user"] == "0xW"
            return Resp({"data": data, "pagination": {"next_cursor": None}})

    got = pt.positions("0xW", http=Http(), sleep=lambda s: None)
    assert [p["slug"] for p in got] == ["atp-fritz-altmaie-2026-10-23"]
    assert got[0]["avg_price"] == 0.7 and got[0]["initial_value"] == pytest.approx(70)    # what the shares held cost


def test_all_time_figures_are_asked_once_and_an_outage_cannot_stall_a_run():
    class Resp:
        def __init__(self, code, data=None): self.status_code, self._d = code, data
        def json(self): return self._d
        def raise_for_status(self): pass

    asked = []

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            assert url.endswith("/v2/leaderboard") and params["time_period"] == "all"
            asked.append(params["user"])
            if params["user"] == "0xa":
                return Resp(200, {"data": {"pnl": -1969623.78, "volume": 69436312.9}})
            return Resp(503)                                          # Polymarket down for everyone else

    figures = pt.alltime_lookup({"0xk": (500.0, 9000.0)}, http=Http(), sleep=lambda s: None)
    assert figures("0xa") == (-1969623.78, 69436312.9) and figures("0xa") == (-1969623.78, 69436312.9)
    assert asked == ["0xa"]                                           # asked once
    assert figures("0xk") == (500.0, 9000.0)                          # unreadable: the last figure known stands in
    assert figures("0xb") is None and figures("0xc") is None          # never known: unknown
    before = len(asked)
    assert figures("0xd") is None and len(asked) == before            # three misses in a row: no more asking


def test_only_the_wallets_in_profit_over_all_time_count():
    lb = pd.DataFrame({"wallet": ["0xl", "0xu", "0xs", "0xz", "0xf", "0xg"], "rank": range(1, 7)})
    alltime = {"0xl": (-55155.0, 5.8e7), "0xs": (135824.0, 7.6e6), "0xz": (0.0, 10.0),
               "0xf": (11152.0, 504765.0), "0xg": (1.0, 2.0)}
    assert list(pt.in_profit(lb, 2, alltime.get)["wallet"]) == ["0xs", "0xf"]     # loss, unknown, nought: out
    assert list(pt.in_profit(lb, 9, alltime.get, depth=3)["wallet"]) == ["0xs"]   # looks no deeper than asked
    by_index = lb.set_index("wallet")
    assert list(pt.in_profit(by_index, 1, alltime.get).index) == ["0xs"]          # a ranking keyed by wallet
    radar = pd.DataFrame({"wallet": ["0xs", "0xn"], "alltime_pnl": [100.0, None], "alltime_vol": [900.0, 5.0]})
    ranking = pd.DataFrame({"wallet": ["0xs"], "alltime_pnl": [135824.0], "alltime_vol": [7.6e6]})
    assert pt.known_alltime(radar, None, ranking) == {"0xs": (135824.0, 7.6e6)}   # the later table wins


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
                   "win_share": 0.6, "live_share": 0.1, "two_sided_share": 0.2, "significant": True}]
                 ).to_csv(tmp_path / "pm_tennis_traders.csv", index=False)
    board = [{"match_id": "7", "date": "2026-10-23", "tournament": "Lyon", "players": ["Fritz T.", "Altmaier D."],
              "fair": [0.78, 0.22], "fair_source": "Pinnacle", "fair_quality": "sharp", "ref_book": "Pinnacle",
              "books": {"Pinnacle": [1.25, 4.3], "bet365": [1.22, 4.5], "TennisExplorer": [1.3, 4.9]},
              "prediction_markets": [{"venue": "Polymarket",
                                      "url": "https://polymarket.com/event/atp-fritz-altmaie-2026-10-23"}]}]
    held = [{"wallet": "0xW", "slug": "atp-fritz-altmaie-2026-10-23", "title": "Lyon", "outcome": "Daniel Altmaier",
             "avg_price": 0.2, "cur_price": 0.24, "size": 500, "initial_value": 100, "current_value": 120}]
    out = bd.pro_positions(board, fetch=lambda w: held, figures=lambda w: (1.0, 2.0))
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
            return _Resp({"data": {"pnl": 25000.0 if params["user"] == "0xA" else -1969623.0, "volume": 1e6}})

    out = pt.mark_elite(lb, http=Http(), sleep=lambda s: None)
    assert out["elite"].tolist() == [True, False, False, False, False]
    assert asked == ["0xA", "0xB"]                                   # all-time looked up only where the rest holds
    assert out.loc[1, "alltime_pnl"] == -1969623.0


def test_a_second_source_in_the_red_rules_a_wallet_out():
    lb = pd.DataFrame([{"wallet": w, "significant": True, "consistent": True, "pnl": 500.0} for w in ("0xA", "0xB", "0xC")])

    class Http:
        def get(self, url, params=None, headers=None, timeout=None):
            return _Resp({"data": {"pnl": 10000.0, "volume": 1e6}})          # all three ahead on Polymarket

    opinions = {"0xA": {"pnl": 75700.0, "winRate": 57.5, "closedPredictions": 1200},
                "0xB": {"pnl": -99504.6, "winRate": 50.4, "closedPredictions": 24749}}
    out = pt.mark_elite(lb, http=Http(), sleep=lambda s: None, second_opinion=opinions.get)
    assert out["elite"].tolist() == [True, False, True]                      # 0xC: page unreadable, no verdict
    assert out.loc[0, "pi_win_rate"] == 57.5 and out.loc[1, "pi_pnl"] == -99504.6
