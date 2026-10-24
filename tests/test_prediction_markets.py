"""Parsers for the two prediction-market feeds, on the shapes seen live on
2026-10-22. No network: the fixtures are trimmed copies of real responses."""
import json

import pandas as pd
import pytest

from tennissharp.data import kalshi, polymarket


def _poly_event(slug="atp-altmaie-fritz-2026-10-23", title="Lyon Open: Daniel Altmaier vs Taylor Fritz",
                kind="moneyline", outcomes=("Daniel Altmaier", "Taylor Fritz")):
    return {
        "id": "1", "title": title, "slug": slug, "startDate": "2026-10-22T17:05:00Z",
        "liquidity": 51969.7, "volume": 6988.4,
        "markets": [
            {"question": "Set handicap", "sportsMarketType": "tennis_set_handicap"},
            {"question": title, "sportsMarketType": kind,
             "outcomes": json.dumps(list(outcomes)), "outcomePrices": json.dumps(["0.225", "0.775"]),
             "bestBid": 0.22, "bestAsk": 0.23, "spread": 0.01, "liquidityNum": 40000.0,
             "volumeNum": 6988.4, "gameStartTime": "2026-10-23 15:00:00+00",
             "clobTokenIds": json.dumps(["111", "222"]), "acceptingOrders": True,
             "feesEnabled": True},
        ],
    }


def test_polymarket_moneyline_becomes_one_oriented_row():
    row = polymarket.parse_event(_poly_event())
    assert row["tour"] == "atp"
    assert row["tournament"] == "Lyon Open"
    assert (row["player_a"], row["player_b"]) == ("Daniel Altmaier", "Taylor Fritz")
    assert row["match_date"] == "2026-10-23"
    assert (row["bid_a"], row["ask_a"]) == (0.22, 0.23)
    # The second outcome's book is the complement of the first's.
    assert row["ask_b"] == 0.78 and row["bid_b"] == 0.77
    assert row["fee_rate"] == 0.05
    assert row["token_a"] == "111"


def test_polymarket_skips_doubles_futures_and_other_market_types():
    assert polymarket.parse_event(_poly_event(slug="atp-doubles-miedobe-cukirom-2026-10-23")) is None
    assert polymarket.parse_event(_poly_event(slug="will-novak-djokovic-retire")) is None
    assert polymarket.parse_event(_poly_event(kind="tennis_set_winner")) is None


def test_polymarket_itf_events_are_kept_with_their_own_tour_label():
    row = polymarket.parse_event(_poly_event(
        slug="itf-podrez1-zavats1-2026-10-23",
        title="W50 Cherbourg-en-Cotentin: Veronika Podrez vs Katarina Zavatska",
        outcomes=("Veronika Podrez", "Katarina Zavatska")))
    assert row["tour"] == "itf"
    assert row["tournament"] == "W50 Cherbourg-en-Cotentin"


def test_polymarket_fee_math_matches_the_published_example():
    # docs: 100 shares at $0.50 in Sports cost $1.25 in fees.
    assert round(100 * (polymarket.taker_cost(0.5) - 0.5), 2) == 1.25
    assert polymarket.effective_odds(0.5) < 2.0
    assert polymarket.effective_odds(1.0) is None


def _kalshi_markets():
    rule = ("If {p} wins the Cobolli vs Nakashima professional tennis match in the "
            "2026 ATP Lyon Quarterfinal after a ball has been played, then the market resolves to Yes.")
    return [
        {"ticker": "KXATPMATCH-26OCT23COBNAK-NAK", "event_ticker": "KXATPMATCH-26OCT23COBNAK",
         "yes_sub_title": "Brandon Nakashima", "yes_bid_dollars": "0.5700", "yes_ask_dollars": "0.6200",
         "yes_bid_size_fp": "50.00", "yes_ask_size_fp": "1.00", "volume_fp": "2.01",
         "expected_expiration_time": "2026-10-23T20:00:00Z", "rules_primary": rule.format(p="Brandon Nakashima")},
        {"ticker": "KXATPMATCH-26OCT23COBNAK-COB", "event_ticker": "KXATPMATCH-26OCT23COBNAK",
         "yes_sub_title": "Flavio Cobolli", "yes_bid_dollars": "0.3500", "yes_ask_dollars": "0.4000",
         "yes_bid_size_fp": "12.00", "yes_ask_size_fp": "5.00", "volume_fp": "26.15",
         "expected_expiration_time": "2026-10-23T20:00:00Z", "rules_primary": rule.format(p="Flavio Cobolli")},
    ]


def test_kalshi_event_is_oriented_by_the_ticker_codes_not_list_order():
    row = kalshi.parse_event_markets(_kalshi_markets(), "KXATPMATCH", "quadratic_with_maker_fees")
    # Event code COBNAK: Cobolli is A although Nakashima's market came first.
    assert (row["player_a"], row["player_b"]) == ("Flavio Cobolli", "Brandon Nakashima")
    assert (row["bid_a"], row["ask_a"]) == (0.35, 0.40)
    assert (row["bid_b"], row["ask_b"]) == (0.57, 0.62)
    assert row["match_date"] == "2026-10-23"
    assert (row["tournament"], row["round"]) == ("ATP Lyon", "Quarterfinal")
    assert row["fee_rate"] == 0.07 and row["maker_fee_rate"] == 0.0175
    assert row["volume"] == pytest.approx(28.16)


def test_kalshi_rules_parser_handles_rounds_it_has_seen():
    assert kalshi.parse_rules("... in the 2026 W100 Wrexham Quarterfinal after a ball has been played") == ("W100 Wrexham", "Quarterfinal")
    assert kalshi.parse_rules("... in the 2026 ATP Challenger Fort Worth Round Of 16 after a ball has been played") == ("ATP Challenger Fort Worth", "Round Of 16")
    assert kalshi.parse_rules("... in the 2026 M15 Bol Round of 32 after a ball has been played") == ("M15 Bol", "Round of 32")
    assert kalshi.parse_rules("nothing here") == (None, None)


def test_kalshi_odd_event_shapes_are_dropped():
    assert kalshi.parse_event_markets(_kalshi_markets()[:1], "KXATPMATCH") is None


def test_kalshi_fee_math_matches_the_published_example():
    # 100 contracts at $0.55 cost $1.74 (0.07 x 100 x 0.55 x 0.45 = 1.7325, rounded up).
    import math
    assert math.ceil(100 * (kalshi.taker_cost(0.55) - 0.55) * 100) / 100 == 1.74
    assert kalshi.effective_odds(0.55) < 1 / 0.55


def test_kalshi_fetch_groups_markets_per_event(monkeypatch):
    calls = []

    def fake_get(path, params, session=None, sleep=None):
        calls.append((path, dict(params)))
        if path == "/markets" and params["series_ticker"] == "KXATPMATCH":
            return {"markets": _kalshi_markets(), "cursor": ""}
        return {"markets": [], "cursor": ""}

    monkeypatch.setattr(kalshi, "_get", fake_get)
    df = kalshi.fetch_moneylines(series=["KXATPMATCH", "KXWTAMATCH"], sleep=lambda s: None)
    assert len(df) == 1
    assert df.iloc[0]["event_ticker"] == "KXATPMATCH-26OCT23COBNAK"
    assert isinstance(df, pd.DataFrame)
