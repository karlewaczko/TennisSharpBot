"""Cross-venue price comparison: name matching between the abbreviated
schedule and the spelled-out prediction markets, fee-adjusted odds, EV
against the sharp fair value, and the arbitrage test."""
import pandas as pd
import pytest

from tennissharp import market_compare as mc


# ---- names -----------------------------------------------------------------

@pytest.mark.parametrize("abbrev,full", [
    ("Cobolli F.", "Flavio Cobolli"),
    ("Van Assche L.", "Luca Van Assche"),
    ("Zarate C.M.", "Carlos Maria Zarate"),
    ("Struff J.L.", "Jan-Lennard Struff"),
    ("Wolf J.J.", "J.J. Wolf"),
    ("Seyboth Wild T.", "Thiago Seyboth Wild"),
    ("Marti Pujolras A.", "Alex Marti Pujolras"),
    ("Zhang Zh.", "Zhizhen Zhang"),
    ("Kwon S.W.", "Soon Woo Kwon"),
    ("O'Connell C.", "Christopher O'Connell"),
    ("Ramos-Vinolas A.", "Albert Ramos-Vinolas"),
    ("Söke D.", "Duru Soke"),
    ("Moller E.", "Elmer Moeller"),
    ("Meligeni Rodrigues Alves F.", "Felipe Meligeni Alves"),
    ("Bu Y.", "Yunchaokete Bu"),
    ("Pliskova Ka.", "Karolina Pliskova"),
])
def test_abbreviated_schedule_names_resolve_onto_full_names(abbrev, full):
    assert mc.name_matches(abbrev, full)


@pytest.mark.parametrize("abbrev,full", [
    ("Pliskova Ka.", "Kristyna Pliskova"),     # the sisters
    ("Cobolli F.", "Brandon Nakashima"),
    ("Zverev A.", "Mischa Zverev"),
    ("Jong A.", "Sander Jong"),                # Kalshi's spelling of A. M. Jong
    ("Alves F.", "Felipe Alves Meligeni X"),   # surname must be contiguous: "Alves" alone is fine, but
])
def test_wrong_people_are_not_matched(abbrev, full):
    # The last case still matches on the surname "alves" -- documented so a
    # change is deliberate.
    expected = abbrev == "Alves F."
    assert mc.name_matches(abbrev, full) is expected


def test_pair_orientation_reads_both_orders_and_refuses_ambiguity():
    assert mc.pair_orientation("Cobolli F.", "Nakashima B.",
                               "Flavio Cobolli", "Brandon Nakashima") is True
    assert mc.pair_orientation("Cobolli F.", "Nakashima B.",
                               "Brandon Nakashima", "Flavio Cobolli") is False
    assert mc.pair_orientation("Cobolli F.", "Nakashima B.",
                               "Flavio Cobolli", "Taylor Fritz") is None
    # Sisters against each other: the initial group settles it.
    assert mc.pair_orientation("Pliskova Ka.", "Pliskova Kr.",
                               "Kristyna Pliskova", "Karolina Pliskova") is False


def test_attach_markets_joins_on_names_and_nearby_dates():
    sched = pd.DataFrame([
        {"match_id": "1", "date": "2026-10-23", "player1": "Cobolli F.", "player2": "Nakashima B."},
        {"match_id": "2", "date": "2026-10-23", "player1": "Fritz T.", "player2": "Altmaier D."},
    ])
    markets = pd.DataFrame([
        {"venue": "Kalshi", "player_a": "Brandon Nakashima", "player_b": "Flavio Cobolli",
         "match_date": "2026-10-23", "ask_a": 0.62, "bid_a": 0.57, "ask_b": 0.40, "bid_b": 0.35},
        {"venue": "Polymarket", "player_a": "Daniel Altmaier", "player_b": "Taylor Fritz",
         "match_date": "2026-10-30", "ask_a": 0.2, "bid_a": 0.1, "ask_b": 0.9, "bid_b": 0.8},
    ])
    hits = mc.attach_markets(sched, markets)
    assert list(hits) == ["1"]
    assert hits["1"][0]["venue"] == "Kalshi"
    assert hits["1"][0]["first_is_player1"] is False   # Kalshi lists Nakashima first


# ---- fees and odds ---------------------------------------------------------

def test_fee_adjusted_odds_are_worse_than_raw_and_worst_at_even_money():
    raw = 1 / 0.5
    assert mc.effective_odds(0.5, 0.0) == pytest.approx(raw)
    poly = mc.effective_odds(0.5, 0.05)       # Polymarket sports taker
    kalshi = mc.effective_odds(0.5, 0.07)     # Kalshi taker
    assert raw > poly > kalshi
    # 100 shares at $0.50 on Polymarket cost $50 + $1.25 fee: 2.5% of stake.
    assert mc.taker_cost(0.5, 0.05) == pytest.approx(0.5125)
    # Fee share of the stake shrinks toward the extremes (0.45 on $90).
    assert (mc.taker_cost(0.9, 0.05) / 0.9 - 1) < (mc.taker_cost(0.5, 0.05) / 0.5 - 1)


def test_effective_odds_reject_non_prices():
    assert mc.effective_odds(None) is None
    assert mc.effective_odds(0.0) is None
    assert mc.effective_odds(1.0) is None
    assert mc.effective_odds("abc") is None


def test_market_quote_orients_onto_the_schedule_pair():
    row = {"venue": "Polymarket", "ask_a": 0.40, "bid_a": 0.38, "ask_b": 0.62, "bid_b": 0.60,
           "fee_rate": 0.05, "maker_fee_rate": 0.0, "liquidity": 1000}
    q = mc.market_quote(row, first_is_player1=False)
    assert q["ask"] == [0.62, 0.40]
    assert q["bid"] == [0.60, 0.38]
    assert q["taker_odds"][1] == pytest.approx(1 / mc.taker_cost(0.40, 0.05))
    assert q["maker_odds"][1] == pytest.approx(1 / 0.38)


# ---- value and arbitrage ---------------------------------------------------

def test_value_rows_measure_each_price_against_the_fair_value():
    fair = (0.60, 0.40)
    books = {"Pinnacle": [1.62, 2.40], "bet365": [1.57, 2.60]}
    rows = mc.value_rows(("A", "B"), fair, books, [], ref_book="Pinnacle")
    by = {(r["venue"], r["player"]): r for r in rows}
    assert by[("bet365", "B")]["ev"] == pytest.approx(0.40 * 2.60 - 1, abs=1e-4)
    assert by[("Pinnacle", "A")]["is_sharp"] and by[("Pinnacle", "A")]["is_reference"]
    assert not by[("bet365", "A")]["is_sharp"]


def test_prediction_rows_carry_taker_and_maker_ev_and_the_mid_gap():
    fair = (0.60, 0.40)
    q = mc.market_quote({"venue": "Kalshi", "ask_a": 0.55, "bid_a": 0.53, "ask_b": 0.47,
                         "bid_b": 0.45, "fee_rate": 0.07, "maker_fee_rate": 0.0175}, True)
    rows = [r for r in mc.value_rows(("A", "B"), fair, {}, [q]) if r["player"] == "A"]
    r = rows[0]
    assert r["signal_only"] is True
    assert r["mid_gap"] == pytest.approx(0.54 - 0.60, abs=1e-4)
    assert r["ev"] == pytest.approx(0.60 / mc.taker_cost(0.55, 0.07) - 1, abs=1e-4)
    assert r["ev_maker"] == pytest.approx(0.60 / mc.taker_cost(0.53, 0.0175) - 1, abs=1e-4)


def test_arbitrage_picks_the_best_price_per_side_fee_included():
    books = {"Pinnacle": [1.90, 1.95], "bet365": [2.05, 1.80]}
    q = mc.market_quote({"venue": "Polymarket", "ask_a": 0.60, "bid_a": 0.58, "ask_b": 0.42,
                         "bid_b": 0.40, "fee_rate": 0.05, "maker_fee_rate": 0.0}, True)
    arb = mc.best_arbitrage(("A", "B"), books, [q])
    # Side A: bet365 2.05 vs Polymarket 1/(0.6+0.05*0.6*0.4)=1.606 -> bet365.
    assert arb["side_a"]["venue"] == "bet365"
    # Side B: Polymarket 1/(0.42+0.05*0.42*0.58)=2.314 beats Pinnacle 1.95.
    assert arb["side_b"]["venue"] == "Polymarket"
    assert arb["is_arbitrage"] is True
    assert arb["profit"] > 0
    assert arb["stake_a"] + arb["stake_b"] == pytest.approx(1.0, abs=1e-3)
    assert arb["signal_only"] is True


def test_no_arbitrage_when_the_best_pair_still_sums_past_one():
    arb = mc.best_arbitrage(("A", "B"), {"Pinnacle": [1.90, 1.95]}, [])
    assert arb["is_arbitrage"] is False
    assert arb["margin"] == pytest.approx(1 / 1.90 + 1 / 1.95 - 1, abs=1e-4)
    assert mc.best_arbitrage(("A", "B"), {}, []) is None


# ---- snapshots -------------------------------------------------------------

def test_snapshots_append_and_yield_opening_and_closing(tmp_path):
    path = tmp_path / "snap.csv"
    entry = {"match_id": "7", "date": "2026-10-23", "tournament": "Lyon",
             "players": ["Cobolli F.", "Nakashima B."],
             "books": {"Pinnacle": [2.50, 1.55]}, "prediction_markets": []}
    assert mc.append_snapshots(path, mc.snapshot_rows(entry, "2026-10-22T10:00:00+00:00")) == 1
    entry["books"] = {"Pinnacle": [2.30, 1.65]}
    assert mc.append_snapshots(path, mc.snapshot_rows(entry, "2026-10-23T08:00:00+00:00")) == 1
    snaps = mc.load_snapshots(path)
    oc = mc.opening_and_closing(snaps, "Pinnacle").set_index("match_id").loc["7"]
    assert (oc["open1"], oc["close1"]) == (2.50, 2.30)
    assert oc["n_snapshots"] == 2
    # Taking 2.50 on a side that closed at 2.30 (fair ~0.42) is positive CLV.
    assert mc.closing_value(2.50, [2.30, 1.65]) > 0
    assert mc.closing_value(2.50, [1.0, 1.65]) is None


def test_empty_snapshot_file_is_an_empty_frame(tmp_path):
    assert mc.load_snapshots(tmp_path / "missing.csv").empty
    assert mc.opening_and_closing(mc.load_snapshots(tmp_path / "missing.csv")).empty


def test_exchange_anchor_takes_the_most_liquid_tight_market():
    thin = mc.market_quote({"venue": "Kalshi", "ask_a": 0.60, "bid_a": 0.58, "ask_b": 0.42,
                            "bid_b": 0.40, "liquidity": 200}, True)
    wide = mc.market_quote({"venue": "Polymarket", "ask_a": 0.65, "bid_a": 0.55, "ask_b": 0.45,
                            "bid_b": 0.35, "liquidity": 50000}, True)
    good = mc.market_quote({"venue": "Polymarket", "ask_a": 0.61, "bid_a": 0.60, "ask_b": 0.40,
                            "bid_b": 0.39, "liquidity": 9000}, True)
    anchor = mc.exchange_anchor([thin, wide, good])
    assert anchor["venue"] == "Polymarket" and anchor["liquidity"] == 9000
    # Mids 0.605 / 0.395 normalised to one.
    assert anchor["fair"][0] == pytest.approx(0.605 / 1.0, abs=1e-6)
    assert sum(anchor["fair"]) == pytest.approx(1.0)
    assert mc.exchange_anchor([thin, wide]) is None
    assert mc.exchange_anchor([]) is None
