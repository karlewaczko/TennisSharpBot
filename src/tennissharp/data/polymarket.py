"""Polymarket tennis moneylines, read from the public Gamma API (no key).

Tennis is tag 864 on Gamma; `/sports` lists ATP (id 45), WTA (46) and ITF
(187) under it. One event is one match -- "Lyon Open: Daniel Altmaier vs
Taylor Fritz", slug `atp-altmaie-fritz-2026-10-23` -- carrying up to 17
markets (sets, games, handicaps). The one read here is the market whose
`sportsMarketType` is "moneyline": its two outcomes are the player names.
Doubles share the tour prefix and carry "-doubles-" in the slug.

Prices. `bestBid`/`bestAsk` quote the token of the FIRST outcome. The second
outcome's book is its complement (ask_b = 1 - bid_a): the two tokens are
minted and merged together for exactly one USDC, so any other price is an
arbitrage inside Polymarket itself.

Fees (docs.polymarket.com/trading/fees, read 2026-10-22): takers only,
fee = shares x rate x p x (1 - p), with rate 0.05 for the Sports category;
makers are never charged. A share bought at price p therefore costs
p + 0.05 p (1 - p) per one USDC of payout -- `taker_cost` below.

Legal. Polymarket geoblocks Germany; the GGL put it on its blacklist in
September 2025 (event contracts are not permissible under the GlüStV 2021).
This module reads public prices as *information about the market*. It
places no orders and is not a venue for a bettor in Germany.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

import pandas as pd
import requests

logger = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com"
TENNIS_TAG_ID = 864
PAGE_SIZE = 100
TAKER_FEE_RATE = 0.05   # Sports category
MAKER_FEE_RATE = 0.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)"}
_TIMEOUT = 30

# Slug prefix -> tour label. Challengers are listed under "atp" (Cali, Fort
# Worth, Lisbon on the first card read), so the label is the circuit the
# event belongs to on Polymarket, not the tournament's tier.
TOUR_BY_PREFIX = {"atp": "atp", "wta": "wta", "itf": "itf"}


def taker_cost(price: float, fee_rate: float = TAKER_FEE_RATE) -> float:
    """What one share paying 1 USDC costs a taker at `price`, fee included."""
    return price + fee_rate * price * (1.0 - price)


def effective_odds(price: float, fee_rate: float = TAKER_FEE_RATE) -> float | None:
    """Decimal odds equivalent of buying at `price` as a taker."""
    if price is None or not (0.0 < price < 1.0):
        return None
    return 1.0 / taker_cost(price, fee_rate)


def fetch_events(start_date_min: str | None = None, max_pages: int = 15,
                 session=None) -> list[dict]:
    """Every open tennis event from `start_date_min` on, paged 100 at a time.

    `start_date_min` filters on the event's creation ("startDate"), which
    for a match is roughly a day before play; one day of slack is enough.
    """
    http = session or requests
    out: list[dict] = []
    for page in range(max_pages):
        params = {"tag_id": TENNIS_TAG_ID, "active": "true", "closed": "false",
                  "limit": PAGE_SIZE, "offset": page * PAGE_SIZE}
        if start_date_min:
            params["start_date_min"] = start_date_min
        resp = http.get(f"{GAMMA_URL}/events", params=params, headers=_HEADERS,
                        timeout=_TIMEOUT)
        resp.raise_for_status()
        batch = resp.json()
        out.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
    return out


def _json_list(raw) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return []


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def parse_event(event: dict) -> dict | None:
    """One row per singles match from an event, or None when it is not one."""
    slug = str(event.get("slug") or "")
    prefix = slug.split("-", 1)[0]
    tour = TOUR_BY_PREFIX.get(prefix)
    if tour is None or "-doubles-" in slug or slug.startswith(f"{prefix}-doubles"):
        return None
    market = next((m for m in event.get("markets", [])
                   if m.get("sportsMarketType") == "moneyline"), None)
    if market is None:
        return None
    outcomes = _json_list(market.get("outcomes"))
    if len(outcomes) != 2:
        return None
    prices = [_num(p) for p in _json_list(market.get("outcomePrices"))]
    bid_a, ask_a = _num(market.get("bestBid")), _num(market.get("bestAsk"))
    title = str(event.get("title") or market.get("question") or "")
    tournament = title.split(":", 1)[0].strip() if ":" in title else ""
    start = market.get("gameStartTime") or event.get("gameStartTime")
    try:
        start_ts = pd.Timestamp(start).tz_convert("UTC") if start else None
    except (TypeError, ValueError):
        start_ts = None
    tokens = _json_list(market.get("clobTokenIds"))
    return {
        "venue": "Polymarket",
        "tour": tour,
        "tournament": tournament,
        "player_a": str(outcomes[0]).strip(),
        "player_b": str(outcomes[1]).strip(),
        "start_time": start_ts,
        "match_date": (start_ts.date().isoformat() if start_ts is not None
                       else (slug[-10:] if slug[-10:-6].isdigit() else None)),
        "mid_a": prices[0] if prices else None,
        "bid_a": bid_a,
        "ask_a": ask_a,
        # Complement book for the second outcome.
        "bid_b": round(1.0 - ask_a, 4) if ask_a is not None else None,
        "ask_b": round(1.0 - bid_a, 4) if bid_a is not None else None,
        "spread": _num(market.get("spread")),
        "liquidity": _num(market.get("liquidityNum")) or _num(event.get("liquidity")),
        "volume": _num(market.get("volumeNum")) or _num(event.get("volume")),
        "accepting_orders": bool(market.get("acceptingOrders", True)),
        "fee_rate": TAKER_FEE_RATE if market.get("feesEnabled", True) else 0.0,
        "maker_fee_rate": MAKER_FEE_RATE,
        "token_a": str(tokens[0]) if len(tokens) == 2 else None,
        "token_b": str(tokens[1]) if len(tokens) == 2 else None,
        "slug": slug,
        "url": f"https://polymarket.com/event/{slug}",
    }


COLUMNS = ("venue", "tour", "tournament", "player_a", "player_b", "start_time",
           "match_date", "mid_a", "bid_a", "ask_a", "bid_b", "ask_b", "spread",
           "liquidity", "volume", "accepting_orders", "fee_rate", "maker_fee_rate",
           "token_a", "token_b", "slug", "url")


def fetch_moneylines(days_back: int = 1, today: dt.date | None = None,
                     session=None) -> pd.DataFrame:
    """Open singles moneylines, newest events first."""
    since = (today or dt.date.today()) - dt.timedelta(days=days_back)
    events = fetch_events(start_date_min=f"{since.isoformat()}T00:00:00Z", session=session)
    rows = [r for r in (parse_event(e) for e in events) if r]
    df = pd.DataFrame(rows, columns=list(COLUMNS))
    logger.info("Polymarket: %d events, %d singles moneylines", len(events), len(df))
    return df
