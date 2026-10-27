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
import json
import logging
import math
import re
import time
from collections import defaultdict

import numpy as np
import pandas as pd
import requests
from scipy.stats import t as student_t

logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
TENNIS_TAG = 864
PAGE = 500
MAX_TRADES_PER_MARKET = 6000
PAUSE = 0.1
TRADE_PAGE = 10000
MIN_PRE_MARKETS = 20       # pre-match markets a wallet needs to be ranked
MIN_STAKE = 2000.0         # USDC staked over the window
MIN_DIRECTIONAL = 0.7      # below this a wallet trades like a market maker
MAX_LIVE_SHARE = 0.5       # above this a wallet is an in-play trader
STATS_MIN_PRE_MARKETS = 10  # enough pre-match matches to show a wallet's CLV at all
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


# A match's event slug ends in its date: "atp-brooksb-maloney-2026-10-23",
# "epl-ars-che-2026-10-18", "nba-mia-cha-2026-10-24". Outrights
# ("atp-tournament-winner-2026-135005") and doubles do not count.
DATED_SLUG = re.compile(r"-\d{4}-\d{2}-\d{2}$")
TENNIS_PREFIXES = ("atp", "wta", "itf")

# Gamma tags whose decided moneylines are walked. Football is one tag over
# all leagues; basketball's leagues are spread over several. American
# football: NFL, college football and the tag CFL and UFL share; baseball:
# MLB and the tag of every other league (NPB, KBO, CPBL, winter leagues).
SPORT_TAGS = {
    "tennis": (864,),
    "soccer": (100350,),
    "basketball": (28, 745, 100149, 102669, 100254, 101178),
    "football": (450, 100351, 1186),
    "baseball": (100381, 678),
}


def is_match_slug(slug: str, sport: str = "tennis") -> bool:
    if not DATED_SLUG.search(slug) or "-doubles-" in slug:
        return False
    return sport != "tennis" or slug.split("-", 1)[0] in TENNIS_PREFIXES


SPORTS_FEE_RATE = 0.05     # Polymarket's sports schedule: rate x p x (1 - p) per share, takers only


def fee_rate(market: dict) -> float:
    """The taker fee rate a market charges (0 where fees are off)."""
    if not market.get("feesEnabled"):
        return 0.0
    sched = market.get("feeSchedule") or {}
    if isinstance(sched, str):
        try:
            sched = json.loads(sched)
        except ValueError:
            sched = {}
    try:
        return float(sched.get("rate", SPORTS_FEE_RATE))
    except (TypeError, ValueError, AttributeError):
        return SPORTS_FEE_RATE


def market_row(market: dict, sport: str = "tennis") -> dict | None:
    """A resolved moneyline market with its winner, or None. A tennis or
    basketball match is one market, its outcomes the two sides; a football
    match is three Yes/No markets (home, draw, away), each its own row."""
    ev = (market.get("events") or [{}])[0]
    slug = str(ev.get("slug") or market.get("slug") or "")
    if not is_match_slug(slug, sport):
        return None
    outcomes = _json_list(market.get("outcomes"))
    prices = [float(p) for p in _json_list(market.get("outcomePrices")) if p not in (None, "")]
    if len(outcomes) != 2 or len(prices) != 2:
        return None
    if prices[0] > 0.98 and prices[1] < 0.02:
        winner = 0
    elif prices[1] > 0.98 and prices[0] < 0.02:
        winner = 1
    else:
        return None                      # void, 50/50 or unresolved
    question = str(market.get("question") or "")
    return {"slug": slug, "tour": slug.split("-", 1)[0], "condition_id": market.get("conditionId"),
            "tournament": question.split(":", 1)[0].strip() if ":" in question else "",
            "label": str(market.get("groupItemTitle") or ""),
            "player_a": str(outcomes[0]).strip(), "player_b": str(outcomes[1]).strip(),
            "winner": winner, "start_ts": _ts(market.get("gameStartTime") or ev.get("gameStartTime")),
            "volume": float(market.get("volumeNum") or 0.0), "fee_rate": fee_rate(market)}


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def closed_markets(days: int = 30, tours=("atp", "wta"), sport: str = "tennis", http=requests,
                   sleep=time.sleep, now: float | None = None, min_volume: float = 0.0,
                   window_days: float = 1.0, ahead_days: float = 8.0) -> list[dict]:
    """Decided moneyline markets whose match started in the last `days`
    days; `tours` keeps tennis to some circuits (None keeps all).

    A moneyline's end date is its start or a week after it, while it can
    be listed weeks ahead (the NFL season in August), so the end dates are
    walked from the window's start to `ahead_days` past now, one window at
    a time: Gamma refuses offsets past about 2000."""
    now = now or time.time()
    since = now - days * 86400
    out, seen = [], set()
    params = {"closed": "true", "sports_market_types": "moneyline", "limit": 100}
    if min_volume:
        params["volume_num_min"] = min_volume
    for tag in SPORT_TAGS[sport]:
        lo, last = since, now + ahead_days * 86400
        while lo < last:
            hi = min(lo + window_days * 86400, last)
            for offset in range(0, 2000, 100):
                try:
                    batch = _get(http, f"{GAMMA_API}/markets",
                                 {**params, "tag_id": tag, "offset": offset,
                                  "end_date_min": _iso(lo), "end_date_max": _iso(hi)}, sleep=sleep)
                except requests.HTTPError as exc:
                    if getattr(exc.response, "status_code", None) == 422:
                        break
                    raise
                for m in batch or []:
                    row = market_row(m, sport)
                    if (row and (tours is None or row["tour"] in tours) and row["start_ts"]
                            and since <= row["start_ts"] <= now and row["volume"] >= min_volume
                            and row["condition_id"] not in seen):
                        seen.add(row["condition_id"])
                        out.append(row)
                if not batch or len(batch) < 100:
                    break
                sleep(PAUSE)
            else:
                logging.getLogger(__name__).warning("tag %s: window from %s has 2000+ markets", tag, _iso(lo))
            lo = hi
    return out


TRADE_FLOORS = (50, 100, 250, 500, 1000, 2500)


def market_trades(condition_id: str, http=requests, sleep=time.sleep) -> tuple[list[dict], float, set]:
    """Every fill of one market, newest first; the smallest trade size that
    was kept (0: all of them); and the taker_key of every taker fill.

    The API hands out 10000 rows a call from offsets up to 10000, so a
    market of up to 20000 fills comes whole. A bigger one (a busy NBA game)
    is fetched again for trades of at least 50, 100, 250 ... dollars until
    it fits, which keeps its pre-match trading whole above that size. The
    taker fills come from the same listing with takerOnly, under the same
    size floor."""
    def fetch(extra):
        rows = []
        for offset in (0, TRADE_PAGE):
            batch = _get(http, f"{DATA_API}/trades",
                         {"market": condition_id, "limit": TRADE_PAGE, "offset": offset,
                          "takerOnly": "false", **extra}, sleep=sleep) or []
            rows.extend(batch)
            if len(batch) < TRADE_PAGE:
                return rows, True
            sleep(PAUSE)
        return rows, False

    trades, whole = fetch({})
    floor = 0.0
    if not whole:
        for f in TRADE_FLOORS:
            trades, whole = fetch({"filterType": "CASH", "filterAmount": f})
            floor = float(f)
            if whole:
                break
        else:
            logging.getLogger(__name__).warning("%s: over 20000 trades of %d$ and more, the oldest are cut off",
                                                condition_id, TRADE_FLOORS[-1])
    size_floor = {"filterType": "CASH", "filterAmount": floor} if floor else {}
    taker_fills, _ = fetch({**size_floor, "takerOnly": "true"})
    return trades, floor, {taker_key(t) for t in taker_fills}


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


def taker_key(t: dict) -> tuple:
    """One fill, recognisable in both the full and the taker-only listing."""
    return (t.get("transactionHash"), str(t.get("proxyWallet") or "").lower(), int(t.get("outcomeIndex", 0)),
            str(t.get("side", "")).upper(), round(float(t.get("size") or 0), 4))


def account_market(trades: list[dict], winner: int, start_ts: float | None, fee_rate: float = 0.0,
                   takers=frozenset()) -> tuple[float | None, list[dict]]:
    """(closing probability of outcome 0, per-wallet rows for this market).

    A taker pays `fee_rate` x p x (1 - p) per share, Polymarket's sports fee
    (makers pay nothing; their rebates are left out). It comes off the
    profit and off the closing-line value of the fill: `clv_net` is what a
    wallet's pre-match fills beat the close by after costs, `clv` the same
    before them. `takers` holds the taker_key of every taker fill."""
    close0 = closing_price(trades, start_ts)
    acc = defaultdict(lambda: {"cash": 0.0, "net": [0.0, 0.0], "stake": 0.0, "pre_stake": 0.0,
                               "live_stake": 0.0, "taker_stake": 0.0, "fees": 0.0, "clv_w": 0.0,
                               "clvn_w": 0.0, "w": 0.0, "n": 0, "sides": set(), "name": "",
                               "pre_net": 0.0, "pre_gross": 0.0})
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
        fee_share = fee_rate * price * (1.0 - price) if takers and taker_key(t) in takers else 0.0
        a["n"] += 1
        a["stake"] += risk
        a["name"] = t.get("name") or t.get("pseudonym") or a["name"]
        a["sides"].add(o if buy else 1 - o)
        if fee_share:
            a["taker_stake"] += risk
            a["fees"] += fee_share * size
            a["cash"] -= fee_share * size
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
                a["clvn_w"] += (clv - fee_share) * risk
                a["w"] += risk
        else:
            a["live_stake"] += risk
    rows = []
    for w, a in acc.items():
        rows.append({"wallet": w, "name": a["name"], "pnl": a["cash"] + a["net"][winner],
                     "stake": a["stake"], "pre_stake": a["pre_stake"], "live_stake": a["live_stake"],
                     "taker_stake": a["taker_stake"], "fees": a["fees"],
                     "clv": (a["clv_w"] / a["w"]) if a["w"] > 0 else None,
                     "clv_net": (a["clvn_w"] / a["w"]) if a["w"] > 0 else None,
                     "both_sides": len(a["sides"]) > 1, "trades": a["n"],
                     "directional": (abs(a["pre_net"]) / a["pre_gross"]) if a["pre_gross"] else None})
    return close0, rows


LEADER_COLUMNS = ["rank", "name", "wallet", "elite", "markets", "pre_markets", "stake", "pnl", "roi", "fees",
                  "clv_net_mean", "clv_net_t", "significant", "clv_net_first", "clv_net_second", "consistent",
                  "alltime_pnl", "alltime_vol", "pi_pnl", "pi_win_rate", "pi_closed", "clv_mean", "clv_t",
                  "win_share", "live_share", "taker_share",
                  "two_sided_share", "directional"]
TABLE_COLUMNS = ["name", "wallet", "markets", "pre_markets", "stake", "pnl", "roi", "fees", "clv_net_mean",
                 "clv_net_t", "clv_mean", "clv_t", "win_share", "live_share", "taker_share", "two_sided_share",
                 "directional"]
MIN_HALF_MATCHES = 5   # pre-match matches in each half of the window for the consistency check
FDR_Q = 0.10   # share of lucky wallets tolerated among those marked significant


def _mean_t(x: pd.Series) -> tuple[float | None, float | None]:
    n = len(x)
    if not n:
        return None, None
    mean, sd = float(x.mean()), (float(x.std(ddof=1)) if n > 1 else 0.0)
    return mean, (mean / (sd / math.sqrt(n)) if n > 1 and sd > 0 else None)


def wallet_table(per_market: pd.DataFrame) -> pd.DataFrame:
    """Every wallet's figures over the window, before any filter or rank."""
    if per_market.empty:
        return pd.DataFrame(columns=TABLE_COLUMNS)
    pm = per_market
    if "clv_net" not in pm:                 # rows from before fees were counted
        pm = pm.assign(clv_net=pm["clv"], fees=0.0, taker_stake=0.0)
    rows = []
    for w, g in pm.groupby("wallet"):
        pre = g[g["clv"].notna()]
        n = len(pre)
        gross, gross_t = _mean_t(pre["clv"])
        net, net_t = _mean_t(pre["clv_net"])
        stake, pnl = float(g["stake"].sum()), float(g["pnl"].sum())
        names = [x for x in g["name"].tolist() if isinstance(x, str) and x]
        rows.append({"name": names[-1] if names else "", "wallet": w, "markets": int(len(g)),
                     "pre_markets": n, "stake": stake, "pnl": pnl, "roi": pnl / stake if stake else None,
                     "fees": float(g["fees"].sum()), "clv_net_mean": net, "clv_net_t": net_t,
                     "clv_mean": gross, "clv_t": gross_t, "win_share": float((g["pnl"] > 0).mean()),
                     "live_share": float(g["live_stake"].sum()) / stake if stake else None,
                     "taker_share": float(g["taker_stake"].sum()) / stake if stake else None,
                     "two_sided_share": float(g["both_sides"].mean()),
                     "directional": float(pre["directional"].mean()) if n else None})
    return pd.DataFrame(rows, columns=TABLE_COLUMNS)


def significant(t: pd.Series, n: pd.Series, q: float = FDR_Q) -> pd.Series:
    """Benjamini-Hochberg over the one-sided p-values of the CLV
    t-statistics: which wallets beat the close by more than luck explains
    among this many wallets, with at most a share q of them lucky."""
    if t.empty:
        return pd.Series(dtype=bool)
    p = pd.Series(student_t.sf(t.astype(float), (n.astype(float) - 1).clip(lower=1)), index=t.index)
    ordered = np.sort(p.values)
    under = ordered <= q * np.arange(1, len(ordered) + 1) / len(ordered)
    if not under.any():
        return pd.Series(False, index=t.index)
    return p <= ordered[np.nonzero(under)[0].max()]


def halves(per_market: pd.DataFrame, markets: pd.DataFrame) -> pd.DataFrame:
    """Each wallet's CLV after fees in the first and in the second half of
    the window (split at the median start). A real edge shows in both."""
    cols = ["clv_net_first", "clv_net_second", "matches_first", "matches_second"]
    col = "clv_net" if "clv_net" in per_market else "clv"
    if per_market.empty or markets is None or markets.empty:
        return pd.DataFrame(columns=cols)
    starts = markets.drop_duplicates("slug")[["slug", "start_ts"]]
    pre = per_market[per_market[col].notna()].merge(starts, on="slug")
    if pre.empty:
        return pd.DataFrame(columns=cols)
    pre = pre.assign(second=pre["start_ts"] >= starts["start_ts"].median())
    g = pre.groupby(["wallet", "second"])[col].agg(["mean", "size"]).unstack()
    pick = lambda stat, half: g[(stat, half)] if (stat, half) in g.columns else np.nan  # noqa: E731
    return pd.DataFrame({"clv_net_first": pick("mean", False), "clv_net_second": pick("mean", True),
                         "matches_first": pick("size", False), "matches_second": pick("size", True)},
                        index=g.index)


def alltime(wallet: str, http=requests, sleep=time.sleep) -> tuple[float, float] | None:
    """A wallet's all-time profit and volume over every Polymarket market,
    the figures its profile shows."""
    try:
        rows = _get(http, f"{DATA_API}/v1/leaderboard",
                    {"user": wallet, "timePeriod": "ALL", "orderBy": "PNL", "category": "OVERALL"}, sleep=sleep)
        return float(rows[0]["pnl"]), float(rows[0]["vol"])
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        return None


def mark_elite(lb: pd.DataFrame, http=requests, sleep=time.sleep, second_opinion=None) -> pd.DataFrame:
    """The very best, the only wallets worth watching: an edge after fees
    beyond luck (`significant`), ahead of the close in both halves of the
    window (`consistent`), in profit after fees over it, and in profit over
    all time on Polymarket's own leaderboard and, where `second_opinion`
    (wallet -> dict or None, e.g. polyinsider.trader) has figures, there
    too. The all-time figures are fetched only for the wallets that pass
    the rest; a second opinion that cannot be read rules nobody out."""
    lb = lb.copy()
    if lb.empty:
        lb["elite"] = pd.Series(dtype=bool)
        return lb
    lb["elite"] = False
    for col in ("alltime_pnl", "alltime_vol", "pi_pnl", "pi_win_rate", "pi_closed"):
        if col not in lb:
            lb[col] = np.nan
    ahead = lb["significant"].astype(bool) & lb["consistent"].astype(bool) & (lb["pnl"] > 0)
    for i in lb.index[ahead]:
        figures = alltime(lb.at[i, "wallet"], http, sleep)
        if figures:
            lb.at[i, "alltime_pnl"], lb.at[i, "alltime_vol"] = figures
            lb.at[i, "elite"] = figures[0] > 0
        sleep(PAUSE)
        if lb.at[i, "elite"] and second_opinion is not None:
            other = second_opinion(lb.at[i, "wallet"])
            if other:
                lb.at[i, "pi_pnl"] = other.get("pnl")
                lb.at[i, "pi_win_rate"] = other.get("winRate")
                lb.at[i, "pi_closed"] = other.get("closedPredictions")
                if other.get("pnl") is not None and other["pnl"] <= 0:
                    lb.at[i, "elite"] = False
    return lb


def leaderboard(per_market: pd.DataFrame, markets: pd.DataFrame | None = None,
                min_pre_markets: int = MIN_PRE_MARKETS,
                min_stake: float = MIN_STAKE,
                min_directional: float = MIN_DIRECTIONAL,
                max_live_share: float = MAX_LIVE_SHARE) -> pd.DataFrame:
    """One row per wallet over the window, ranked by the t-statistic of its
    closing-line value after fees.

    Wallets that end their pre-match trading close to flat are market
    makers: their closing-line value is the spread they earn, steady enough
    to top a t-statistic, and their holdings are inventory rather than
    opinions. `directional` (mean |net| / gross pre-match shares) keeps
    them out of the ranking. So does a mostly in-play book: nine dollars in
    ten on Polymarket's tennis trade during the match, much of it bots on
    the live score, whose holdings last seconds and are no tip to follow.

    Among hundreds of wallets some beat the close by luck alone, so
    `significant` marks the ones whose edge after fees survives a
    false-discovery check (FDR_Q); only those are worth watching."""
    if per_market.empty:
        return pd.DataFrame(columns=LEADER_COLUMNS)
    lb = wallet_table(per_market)
    lb = lb[(lb["pre_markets"] >= min_pre_markets) & (lb["stake"] >= min_stake) & lb["clv_net_t"].notna()
            & (lb["directional"] >= min_directional) & (lb["live_share"] <= max_live_share)].copy()
    lb["significant"] = significant(lb["clv_net_t"], lb["pre_markets"])
    h = halves(per_market, markets)
    lb = lb.merge(h, left_on="wallet", right_index=True, how="left")
    lb["consistent"] = ((lb["clv_net_first"] > 0) & (lb["clv_net_second"] > 0)
                        & (lb["matches_first"] >= MIN_HALF_MATCHES) & (lb["matches_second"] >= MIN_HALF_MATCHES))
    lb = lb.sort_values(["clv_net_t", "pnl"], ascending=[False, False]).reset_index(drop=True)
    lb.insert(0, "rank", range(1, len(lb) + 1))
    return lb.reindex(columns=LEADER_COLUMNS)


def by_event(per_market: pd.DataFrame) -> pd.DataFrame:
    """One row per wallet and match. A football match is three markets
    (home, draw, away), and a wallet's trades in them are one opinion:
    profit, stakes and fees add up, CLV and direction are weighted by the
    pre-match stake."""
    if per_market.empty or not per_market.duplicated(["wallet", "slug"]).any():
        return per_market
    names = per_market["name"].fillna("").astype(str)
    pm = per_market.assign(
        name=names.where(names != ""),          # so the last *given* name wins
        _cw=per_market["pre_stake"].where(per_market["clv"].notna(), 0.0),
        _dw=per_market["pre_stake"].where(per_market["directional"].notna(), 0.0))
    pm = pm.assign(_c=pm["clv"].fillna(0) * pm["_cw"], _d=pm["directional"].fillna(0) * pm["_dw"])
    extra = {}
    if "clv_net" in pm:
        pm = pm.assign(_n=pm["clv_net"].fillna(0) * pm["_cw"])
        extra = {"_n": ("_n", "sum"), "fees": ("fees", "sum"), "taker_stake": ("taker_stake", "sum")}
    out = pm.groupby(["wallet", "slug"], sort=False).agg(
        name=("name", "last"), pnl=("pnl", "sum"), stake=("stake", "sum"),
        pre_stake=("pre_stake", "sum"), live_stake=("live_stake", "sum"),
        both_sides=("both_sides", "max"), trades=("trades", "sum"),
        _c=("_c", "sum"), _cw=("_cw", "sum"), _d=("_d", "sum"), _dw=("_dw", "sum"), **extra).reset_index()
    out["name"] = out["name"].fillna("")
    out["clv"] = (out["_c"] / out["_cw"]).where(out["_cw"] > 0)
    if "_n" in out:
        out["clv_net"] = (out["_n"] / out["_cw"]).where(out["_cw"] > 0)
    out["directional"] = (out["_d"] / out["_dw"]).where(out["_dw"] > 0)
    return out.drop(columns=[c for c in ("_c", "_cw", "_d", "_dw", "_n") if c in out])


def market_structure(per_market: pd.DataFrame) -> dict:
    """Where the money is: total stake, the share traded in play, and how
    much of it the 20 biggest wallets move."""
    if per_market.empty:
        return {}
    g = per_market.groupby("wallet")[["stake", "pre_stake", "live_stake"]].sum()
    total, pre = float(g["stake"].sum()), float(g["pre_stake"].sum())
    return {"stake_usd": round(total), "in_play_share": round(float(g["live_stake"].sum()) / total, 3),
            "top20_share": round(float(g["stake"].nlargest(20).sum()) / total, 3),
            "top20_pre_match_share": round(float(g["pre_stake"].nlargest(20).sum()) / pre, 3) if pre else None}


def persistence(per_market: pd.DataFrame, markets: pd.DataFrame, min_each: int = 10) -> dict:
    """Does beating the close carry over? The window is cut in two at the
    median start, and a wallet's mean pre-match CLV in the first half is
    set against its mean in the second, for wallets with `min_each`
    pre-match markets in both halves."""
    if per_market.empty or markets.empty:
        return {"wallets": 0}
    cut = markets["start_ts"].median()
    col = "clv_net" if "clv_net" in per_market else "clv"
    starts = markets.drop_duplicates("slug")[["slug", "start_ts"]]
    pre = per_market[per_market[col].notna()].merge(starts, on="slug")
    pre = pre.assign(half=(pre["start_ts"] >= cut).astype(int))
    h = pre.groupby(["wallet", "half"])[col].agg(["mean", "size"]).unstack()
    if ("size", 1) not in h.columns:
        return {"wallets": 0}
    both = h[(h[("size", 0)] >= min_each) & (h[("size", 1)] >= min_each)]
    if len(both) < 20:
        return {"wallets": int(len(both))}
    first, second = both[("mean", 0)], both[("mean", 1)]
    top, bottom = first >= first.quantile(0.9), first <= first.quantile(0.1)
    return {"wallets": int(len(both)), "corr": round(float(first.corr(second)), 3),
            "rank_corr": round(float(first.rank().corr(second.rank())), 3),
            "top_decile_next": round(float(second[top].mean()), 4),
            "bottom_decile_next": round(float(second[bottom].mean()), 4),
            "all_next": round(float(second.mean()), 4)}


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
