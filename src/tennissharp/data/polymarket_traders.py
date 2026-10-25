"""Who trades tennis well on Polymarket, and what they hold right now.

Polymarket settles on a public blockchain, so every fill carries the
trader's wallet and public profile name (data-api.polymarket.com/trades).
Kalshi publishes its trades without any trader identity -- nobody can be
followed there.

Method, per closed singles moneyline of the last N days:

1. Result from the final outcome prices (1/0) and the scheduled start.
2. Every fill, maker and taker side. Per wallet: the cash flow of its buys
   and sells plus the payout of the shares it still held at resolution is
   its profit. Splits and merges need no special case: a YES+NO pair is
   always worth one dollar, so a share sold without having been bought is
   a short the same formula settles correctly.
3. The closing price is the last fill before the scheduled start. A
   pre-match buy at p of an outcome that closed at c beat the close by
   c - p, a sell by p - c. That closing-line value, averaged per market and
   tested across markets (t-statistic), is the skill measure. Profit alone
   ranks luck as well: a wallet up $5,000 over twelve matches says little.

Profiles are pseudonymous and public on polymarket.com; nothing here
links a wallet to a person. Polymarket is not available from Germany:
this is information about the market, not a place to bet.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import re
import time
from collections import defaultdict

import pandas as pd
import requests

logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
TENNIS_TAG = 864
PAGE = 500
MAX_TRADES_PER_MARKET = 6000
PAUSE = 0.1
TRADE_PAGE = 10000
MIN_PRE_MARKETS = 10       # pre-match markets a wallet needs to be ranked
MIN_STAKE = 2000.0         # USDC staked over the window
MIN_DIRECTIONAL = 0.5      # below this a wallet trades like a market maker
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)"}


def _get(http, url, params=None, sleep=time.sleep, attempts=4):
    last = None
    for i in range(attempts):
        try:
            r = http.get(url, params=params, headers=_HEADERS, timeout=30)
        except requests.RequestException as exc:
            last = exc
            sleep(1.5 * (i + 1))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            last = RuntimeError(f"HTTP {r.status_code}")
            sleep(2.0 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"{url} failed: {last}")


def _ts(value) -> float | None:
    if not value:
        return None
    try:
        return pd.Timestamp(value).tz_convert("UTC").timestamp()
    except (TypeError, ValueError):
        try:
            return pd.Timestamp(value, tz="UTC").timestamp()
        except (TypeError, ValueError):
            return None


def _json_list(raw):
    import json
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []


# A singles match: "atp-brooksb-maloney-2026-10-23". The circuits' outrights
# ("atp-tournament-winner-2026-135005") and doubles share the prefix.
MATCH_SLUG = re.compile(r"^(atp|wta|itf)-.+-\d{4}-\d{2}-\d{2}$")


def is_match_slug(slug: str) -> bool:
    return bool(MATCH_SLUG.match(slug)) and "-doubles-" not in slug


def closed_market_row(event: dict) -> dict | None:
    """A resolved singles moneyline with its winner, or None."""
    slug = str(event.get("slug") or "")
    tour = slug.split("-", 1)[0]
    if not is_match_slug(slug):
        return None
    m = next((x for x in event.get("markets", []) if x.get("sportsMarketType") == "moneyline"), None)
    if not m:
        return None
    outcomes = _json_list(m.get("outcomes"))
    prices = [float(p) for p in _json_list(m.get("outcomePrices")) if p not in (None, "")]
    if len(outcomes) != 2 or len(prices) != 2:
        return None
    if prices[0] > 0.98 and prices[1] < 0.02:
        winner = 0
    elif prices[1] > 0.98 and prices[0] < 0.02:
        winner = 1
    else:
        return None                      # void, 50/50 or unresolved
    start = _ts(m.get("gameStartTime") or event.get("gameStartTime"))
    title = str(event.get("title") or "")
    return {"slug": slug, "tour": tour, "condition_id": m.get("conditionId"),
            "tournament": title.split(":", 1)[0].strip() if ":" in title else "",
            "player_a": str(outcomes[0]).strip(), "player_b": str(outcomes[1]).strip(),
            "winner": winner, "start_ts": start, "volume": float(m.get("volumeNum") or 0.0)}


# Finished matches are listed under the shared Tennis tag only; the circuit
# tags (ATP 101232, WTA 102123, ITF 104923) hold the outrights.
TENNIS_TAG = 864


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def closed_markets(days: int = 30, tours=("atp", "wta"), http=requests, sleep=time.sleep,
                   now: float | None = None, min_volume: float = 0.0,
                   window_days: float = 1.0) -> list[dict]:
    """Decided singles moneylines whose match started in the last `days` days.

    Finished matches sit under the shared Tennis tag only (the circuit tags
    hold the outrights), and Gamma refuses offsets past about 2000, so the
    events' creation dates are walked one window at a time."""
    now = now or time.time()
    since = now - days * 86400
    out, seen = [], set()
    lo = since - 3 * 86400            # events are created a day or so before play
    while lo < now:
        hi = min(lo + window_days * 86400, now)
        for offset in range(0, 2000, 100):
            try:
                batch = _get(http, f"{GAMMA_API}/events",
                             {"tag_id": TENNIS_TAG, "closed": "true", "limit": 100, "offset": offset,
                              "start_date_min": _iso(lo), "start_date_max": _iso(hi)}, sleep=sleep)
            except requests.HTTPError as exc:
                if getattr(exc.response, "status_code", None) == 422:
                    break
                raise
            for e in batch or []:
                row = closed_market_row(e)
                if (row and row["tour"] in tours and row["start_ts"] and since <= row["start_ts"] <= now
                        and (row.get("volume") or 0) >= min_volume and row["condition_id"] not in seen):
                    seen.add(row["condition_id"])
                    out.append(row)
            if not batch or len(batch) < 100:
                break
            sleep(PAUSE)
        else:
            logging.getLogger(__name__).warning("window from %s has 2000+ events; narrow window_days", _iso(lo))
        lo = hi
    return out


def market_trades(condition_id: str, http=requests, sleep=time.sleep) -> list[dict]:
    """Every fill of one market, newest first. One request holds a whole
    match: the API takes up to 10000 rows and returns nothing past that
    offset, so a market that fills the page has lost its oldest
    (pre-match) trades and is flagged."""
    trades = _get(http, f"{DATA_API}/trades",
                  {"market": condition_id, "limit": TRADE_PAGE, "offset": 0, "takerOnly": "false"},
                  sleep=sleep) or []
    if len(trades) >= TRADE_PAGE:
        logging.getLogger(__name__).warning("%s: %d trades, the oldest are cut off", condition_id, len(trades))
    return trades


def closing_price(trades: list[dict], start_ts: float | None) -> float | None:
    """Probability of outcome 0 at the last fill before the start."""
    if start_ts is None:
        return None
    pre = [t for t in trades if float(t.get("timestamp", 0)) < start_ts]
    if not pre:
        return None
    last = max(pre, key=lambda t: float(t["timestamp"]))
    p = float(last["price"])
    return p if int(last.get("outcomeIndex", 0)) == 0 else 1.0 - p


def account_market(trades: list[dict], winner: int, start_ts: float | None) -> tuple[float | None, list[dict]]:
    """(closing probability of outcome 0, per-wallet rows for this market)."""
    close0 = closing_price(trades, start_ts)
    acc = defaultdict(lambda: {"cash": 0.0, "net": [0.0, 0.0], "stake": 0.0, "pre_stake": 0.0,
                               "live_stake": 0.0, "clv_w": 0.0, "w": 0.0, "n": 0,
                               "sides": set(), "name": "", "pre_net": 0.0, "pre_gross": 0.0})
    for t in trades:
        w = str(t.get("proxyWallet") or "")
        if not w:
            continue
        a = acc[w]
        size, price = float(t.get("size") or 0), float(t.get("price") or 0)
        o = int(t.get("outcomeIndex", 0))
        buy = str(t.get("side", "")).upper() == "BUY"
        pre = start_ts is not None and float(t.get("timestamp", 0)) < start_ts
        risk = size * price if buy else size * (1.0 - price)
        a["n"] += 1
        a["stake"] += risk
        a["name"] = t.get("name") or t.get("pseudonym") or a["name"]
        a["sides"].add(o if buy else 1 - o)
        if buy:
            a["cash"] -= size * price
            a["net"][o] += size
        else:
            a["cash"] += size * price
            a["net"][o] -= size
        if pre:
            a["pre_stake"] += risk
            # Exposure in outcome-0 shares: buying 0 or selling 1 is long 0. A
            # market maker fills both ways and ends the pre-match flat.
            a["pre_net"] += size if (o == 0) == buy else -size
            a["pre_gross"] += size
            if close0 is not None:
                close_o = close0 if o == 0 else 1.0 - close0
                clv = (close_o - price) if buy else (price - close_o)
                a["clv_w"] += clv * risk
                a["w"] += risk
        else:
            a["live_stake"] += risk
    rows = []
    for w, a in acc.items():
        rows.append({"wallet": w, "name": a["name"], "pnl": a["cash"] + a["net"][winner],
                     "stake": a["stake"], "pre_stake": a["pre_stake"], "live_stake": a["live_stake"],
                     "clv": (a["clv_w"] / a["w"]) if a["w"] > 0 else None,
                     "both_sides": len(a["sides"]) > 1, "trades": a["n"],
                     "directional": (abs(a["pre_net"]) / a["pre_gross"]) if a["pre_gross"] else None})
    return close0, rows


LEADER_COLUMNS = ["rank", "name", "wallet", "markets", "pre_markets", "stake", "pnl", "roi",
                  "clv_mean", "clv_t", "win_share", "live_share", "two_sided_share", "directional"]


def leaderboard(per_market: pd.DataFrame, min_pre_markets: int = MIN_PRE_MARKETS,
                min_stake: float = MIN_STAKE,
                min_directional: float = MIN_DIRECTIONAL) -> pd.DataFrame:
    """One row per wallet over the window, ranked by closing-line t-statistic.

    Wallets that end their pre-match trading close to flat are market
    makers: their closing-line value is the spread they earn, steady enough
    to top a t-statistic, and their holdings are inventory rather than
    opinions. `directional` (mean |net| / gross pre-match shares) keeps
    them out of the ranking."""
    if per_market.empty:
        return pd.DataFrame(columns=LEADER_COLUMNS)
    rows = []
    for w, g in per_market.groupby("wallet"):
        pre = g[g["clv"].notna()]
        n = len(pre)
        mean = float(pre["clv"].mean()) if n else None
        sd = float(pre["clv"].std(ddof=1)) if n > 1 else None
        t = (mean / (sd / math.sqrt(n))) if (n > 1 and sd and sd > 0) else None
        stake = float(g["stake"].sum())
        names = [x for x in g["name"].tolist() if x]
        rows.append({"name": names[-1] if names else "", "wallet": w, "markets": int(len(g)),
                     "pre_markets": n, "stake": stake, "pnl": float(g["pnl"].sum()),
                     "roi": float(g["pnl"].sum()) / stake if stake else None,
                     "clv_mean": mean, "clv_t": t,
                     "win_share": float((g["pnl"] > 0).mean()),
                     "live_share": float(g["live_stake"].sum()) / stake if stake else None,
                     "two_sided_share": float(g["both_sides"].mean()),
                     "directional": float(pre["directional"].mean()) if n else None})
    lb = pd.DataFrame(rows)
    lb = lb[(lb["pre_markets"] >= min_pre_markets) & (lb["stake"] >= min_stake) & lb["clv_t"].notna()
            & (lb["directional"] >= min_directional)]
    lb = lb.sort_values(["clv_t", "pnl"], ascending=[False, False]).reset_index(drop=True)
    lb.insert(0, "rank", range(1, len(lb) + 1))
    return lb.reindex(columns=LEADER_COLUMNS)


def calibration(markets: pd.DataFrame) -> dict:
    """How good Polymarket's closing prices are as forecasts."""
    m = markets.dropna(subset=["close_a"])
    if m.empty:
        return {"n": 0}
    p = m["close_a"].clip(1e-4, 1 - 1e-4)
    y = (m["winner"] == 0).astype(float)
    bins = pd.cut(p, [0, .2, .35, .5, .65, .8, 1.0], include_lowest=True)
    cal = (pd.DataFrame({"p": p, "y": y, "b": bins}).groupby("b", observed=True)
           .agg(n=("y", "size"), price=("p", "mean"), won=("y", "mean")).reset_index())
    return {"n": int(len(m)),
            "brier": round(float(((p - y) ** 2).mean()), 4),
            "log_loss": round(float(-(y * p.map(math.log) + (1 - y) * (1 - p).map(math.log)).mean()), 4),
            "favourite_won": round(float(((p >= .5) == (y == 1)).mean()), 3),
            "bins": [{"range": str(r.b), "n": int(r.n), "price": round(float(r.price), 3),
                      "won": round(float(r.won), 3)} for r in cal.itertuples()]}


def positions(wallet: str, http=requests, sleep=time.sleep) -> list[dict]:
    """A wallet's open tennis singles positions."""
    data = _get(http, f"{DATA_API}/positions",
                {"user": wallet, "limit": 500, "sizeThreshold": 1}, sleep=sleep) or []
    out = []
    for p in data:
        slug = str(p.get("eventSlug") or p.get("slug") or "")
        if not is_match_slug(slug):
            continue
        cur = float(p.get("curPrice") or 0)
        if p.get("redeemable") or not (0.02 < cur < 0.98):
            continue
        out.append({"wallet": wallet, "slug": slug, "title": p.get("title"),
                    "outcome": p.get("outcome"), "avg_price": float(p.get("avgPrice") or 0),
                    "cur_price": cur, "size": float(p.get("size") or 0),
                    "initial_value": float(p.get("initialValue") or 0),
                    "current_value": float(p.get("currentValue") or 0)})
    return out
