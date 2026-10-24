"""Kalshi tennis match markets, read from the public trade API (no key for
market data).

Each match is one *event* with two binary *markets*, one per player
("Flavio Cobolli wins"), under a series per circuit: KXATPMATCH, KXWTAMATCH,
KXATPCHALLENGERMATCH, KXWTACHALLENGERMATCH, KXITFMATCH (men's ITF),
KXITFWMATCH. The event ticker encodes the pairing in order --
KXATPMATCH-26OCT23COBNAK is Cobolli (COB) then Nakashima (NAK) -- and each
market's ticker ends in its own player's code, which fixes the orientation.
Tournament and round are only stated in prose, in `rules_primary`:
"... in the 2026 ATP Lyon Quarterfinal after a ball has been played".

Prices come as decimal strings in `yes_bid_dollars` / `yes_ask_dollars`,
sizes in `*_size_fp` contracts. The legacy cent fields are null.

Fees (series `fee_type`, read 2026-10-22): "quadratic" is the exchange's
standard taker fee, 0.07 x contracts x P x (1 - P), rounded up to the cent
per order, makers free; "quadratic_with_maker_fees" (KXATPMATCH, KXWTAMATCH)
also charges resting orders, at a quarter of the rate, 0.0175. The
per-contract approximation used here ignores the cent rounding.

Legal. Kalshi is a US-regulated exchange open to US residents; it is not a
venue for a bettor in Germany. Its prices are read as information only.
"""
from __future__ import annotations

import logging
import re
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
MATCH_SERIES = {
    "KXATPMATCH": "atp",
    "KXWTAMATCH": "wta",
    "KXATPCHALLENGERMATCH": "atp",
    "KXWTACHALLENGERMATCH": "wta",
    "KXITFMATCH": "itf",
    "KXITFWMATCH": "itf",
}
TAKER_FEE_RATE = 0.07
MAKER_FEE_RATE = {"quadratic": 0.0, "quadratic_with_maker_fees": 0.0175}
PAGE_SIZE = 200
REQUEST_PAUSE = 0.4
ATTEMPTS = 4
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)",
            "Accept": "application/json"}
_TIMEOUT = 30

_RULES_RE = re.compile(
    r"in the (?P<year>\d{4}) (?P<rest>.+?) after a ball has been played", re.IGNORECASE)
_ROUND_RE = re.compile(
    r"\s(?P<round>Final|Semifinal|Quarterfinal|Round of \d+|\d+(?:st|nd|rd|th) Round|"
    r"Qualif\w+(?: \w+)*|Group Stage|Round Robin)$", re.IGNORECASE)


def taker_cost(price: float, fee_rate: float = TAKER_FEE_RATE) -> float:
    return price + fee_rate * price * (1.0 - price)


def effective_odds(price: float, fee_rate: float = TAKER_FEE_RATE) -> float | None:
    if price is None or not (0.0 < price < 1.0):
        return None
    return 1.0 / taker_cost(price, fee_rate)


def _get(path: str, params: dict, session=None, sleep=time.sleep) -> dict:
    http = session or requests
    last = None
    for attempt in range(ATTEMPTS):
        resp = http.get(f"{BASE_URL}{path}", params=params, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code == 429:
            # The public API rate-limits bursts; one of six series requests
            # hit it on the first live read. Back off and try again.
            last = resp
            sleep(1.5 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    last.raise_for_status()
    return {}


def fetch_markets(series_ticker: str, status: str = "open", session=None,
                  sleep=time.sleep) -> list[dict]:
    out, cursor = [], None
    while True:
        params = {"series_ticker": series_ticker, "status": status, "limit": PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        data = _get("/markets", params, session=session, sleep=sleep)
        out.extend(data.get("markets", []))
        cursor = data.get("cursor")
        if not cursor:
            break
        sleep(REQUEST_PAUSE)
    return out


def fetch_series(series_ticker: str, session=None) -> dict:
    return _get(f"/series/{series_ticker}", {}, session=session).get("series", {})


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def parse_rules(text: str) -> tuple[str | None, str | None]:
    """("ATP Lyon", "Quarterfinal") out of the market's resolution sentence."""
    m = _RULES_RE.search(text or "")
    if not m:
        return None, None
    rest = m.group("rest").strip()
    r = _ROUND_RE.search(rest)
    if r:
        return rest[: r.start()].strip() or None, r.group("round")
    return rest, None


def parse_event_markets(markets: list[dict], series_ticker: str,
                        fee_type: str = "quadratic") -> dict | None:
    """Two per-player markets of one event -> one match row, A then B as the
    event ticker orders them."""
    if len(markets) != 2:
        return None
    event_ticker = str(markets[0].get("event_ticker") or "")
    tail = event_ticker.rsplit("-", 1)[-1]          # 26OCT23COBNAK
    codes = tail[-6:] if len(tail) >= 6 else ""
    by_code = {str(m.get("ticker", "")).rsplit("-", 1)[-1]: m for m in markets}
    a = by_code.get(codes[:3])
    b = by_code.get(codes[3:])
    if a is None or b is None:
        a, b = markets
    tournament, rnd = parse_rules(str(a.get("rules_primary") or ""))
    exp = a.get("expected_expiration_time")
    try:
        exp_ts = pd.Timestamp(exp).tz_convert("UTC") if exp else None
    except (TypeError, ValueError):
        exp_ts = None
    date_code = tail[:7]                             # 26OCT23
    try:
        match_date = pd.Timestamp(f"20{date_code[:2]}-{date_code[2:5]}-{date_code[5:7]}").date().isoformat()
    except (TypeError, ValueError):
        match_date = exp_ts.date().isoformat() if exp_ts is not None else None
    return {
        "venue": "Kalshi",
        "tour": MATCH_SERIES.get(series_ticker, "atp"),
        "series": series_ticker,
        "tournament": tournament,
        "round": rnd,
        "player_a": str(a.get("yes_sub_title") or "").strip(),
        "player_b": str(b.get("yes_sub_title") or "").strip(),
        "match_date": match_date,
        "expires": exp_ts,
        "bid_a": _num(a.get("yes_bid_dollars")),
        "ask_a": _num(a.get("yes_ask_dollars")),
        "bid_b": _num(b.get("yes_bid_dollars")),
        "ask_b": _num(b.get("yes_ask_dollars")),
        "bid_size_a": _num(a.get("yes_bid_size_fp")),
        "ask_size_a": _num(a.get("yes_ask_size_fp")),
        "bid_size_b": _num(b.get("yes_bid_size_fp")),
        "ask_size_b": _num(b.get("yes_ask_size_fp")),
        "volume": (_num(a.get("volume_fp")) or 0.0) + (_num(b.get("volume_fp")) or 0.0),
        # Dollars available to a taker at the best asks on both sides -- the
        # closest thing to Polymarket's liquidity figure the feed offers.
        "liquidity": sum((_num(m.get("yes_ask_size_fp")) or 0.0) * (_num(m.get("yes_ask_dollars")) or 0.0)
                         for m in (a, b)),
        "fee_rate": TAKER_FEE_RATE,
        "maker_fee_rate": MAKER_FEE_RATE.get(fee_type, 0.0),
        "event_ticker": event_ticker,
        "ticker_a": a.get("ticker"),
        "ticker_b": b.get("ticker"),
        "url": f"https://kalshi.com/markets/{series_ticker.lower()}/"
               f"{series_ticker.lower()}/{event_ticker.lower()}",
    }


COLUMNS = ("venue", "tour", "series", "tournament", "round", "player_a", "player_b",
           "match_date", "expires", "bid_a", "ask_a", "bid_b", "ask_b",
           "bid_size_a", "ask_size_a", "bid_size_b", "ask_size_b", "volume", "liquidity",
           "fee_rate", "maker_fee_rate", "event_ticker", "ticker_a", "ticker_b", "url")


def fetch_moneylines(series: list[str] | None = None, session=None,
                     sleep=time.sleep) -> pd.DataFrame:
    rows = []
    for ticker in (series or list(MATCH_SERIES)):
        try:
            markets = fetch_markets(ticker, session=session, sleep=sleep)
        except requests.RequestException as exc:
            logger.warning("Kalshi %s unavailable (%s)", ticker, exc)
            continue
        fee_type = "quadratic_with_maker_fees" if ticker in ("KXATPMATCH", "KXWTAMATCH") \
            else "quadratic"
        by_event: dict[str, list[dict]] = {}
        for m in markets:
            by_event.setdefault(str(m.get("event_ticker")), []).append(m)
        for group in by_event.values():
            row = parse_event_markets(group, ticker, fee_type)
            if row:
                rows.append(row)
        sleep(REQUEST_PAUSE)
    df = pd.DataFrame(rows, columns=list(COLUMNS))
    logger.info("Kalshi: %d match events across %d series", len(df),
                len(series or MATCH_SERIES))
    return df
