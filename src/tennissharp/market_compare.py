"""Compare one match's prices across venues: the sharp book's fair value,
soft bookmakers, and the prediction markets.

Three questions, each answered as plain arithmetic on the quotes so the
dashboard's numbers can be checked by hand:

1. Does a soft book pay more than the sharp fair value is worth?
   `ev = fair_prob x price - 1` with `fair_prob` from the sharp book's
   de-vigged pair. A price merely above the sharp book's *offered* odds is
   not enough -- that comparison still contains the sharp book's margin.
2. Does a prediction market disagree with the sharp book? A share bought at
   price p pays 1, so its decimal odds are 1/p *before* fees. Both venues
   charge takers `rate x p x (1 - p)` per share (Polymarket 0.05 on sports,
   Kalshi 0.07), which `effective_odds` folds into the price. Resting
   (maker) orders are free on Polymarket and on most Kalshi series.
3. Is there an arbitrage? Best price per side over every venue; the pair is
   an arbitrage when 1/o_a + 1/o_b < 1.

Name matching. TennisExplorer abbreviates ("Van Assche L.", "Zarate C.M.",
"Pliskova Ka."); the prediction markets spell names out ("Luca Van Assche").
`name_matches` requires the abbreviated surname's tokens to appear in order
inside the full name and the first initial group to open one of the
remaining tokens -- so "Ka." takes Karolina and not Kristyna, and "J.L."
takes Jan-Lennard. A pairing is accepted only when each schedule name
matches exactly one of the two market names (`pair_orientation`), which is
what keeps a surname shared across two matches from crossing wires.
"""
from __future__ import annotations

import datetime as dt
import functools
import re
import unicodedata
from pathlib import Path

import pandas as pd

from tennissharp import odds_math

SHARP_BOOKS = ("Pinnacle", "Betfair")
PREDICTION_VENUES = ("Polymarket", "Kalshi")
# Venues a bettor in Germany cannot use: Kalshi is US-only, Polymarket is
# geoblocked and on the GGL blacklist, the Betfair exchange left the German
# market. Their prices are information, not an offer.
SIGNAL_ONLY_VENUES = ("Polymarket", "Kalshi", "Betfair")
# The schedule page's own odds pair comes from an unnamed book and stays on
# the page after kick-off. It is shown, but it is nobody's offer, so it takes
# no part in the arbitrage test.
UNNAMED_VENUES = ("TennisExplorer",)


# ---------------------------------------------------------------- fees ----

def taker_cost(price: float, fee_rate: float) -> float:
    return price + fee_rate * price * (1.0 - price)


def effective_odds(price, fee_rate: float = 0.0):
    """Decimal odds of a 1-unit share bought at `price`, fee included."""
    if price is None:
        return None
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if not (0.0 < p < 1.0):
        return None
    return 1.0 / taker_cost(p, fee_rate)


# -------------------------------------------------------------- names ----

def _ascii(text: str) -> str:
    """Accent-stripped lower case, with the German transliterations folded
    too: TennisExplorer writes "Moller E." for the player Polymarket lists as
    "Elmer Moeller"."""
    folded = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return folded.replace("ae", "a").replace("oe", "o").replace("ue", "u")


@functools.lru_cache(maxsize=4096)
def tokens(name: str) -> tuple[str, ...]:
    return tuple(t for t in re.split(r"[^a-z]+", _ascii(name)) if t)


@functools.lru_cache(maxsize=4096)
def split_abbreviated(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """'Van Assche L.' -> (('van','assche'), ('l',)); 'Zarate C.M.' ->
    (('zarate',), ('c','m')); 'Pliskova Ka.' -> (('pliskova',), ('ka',)).
    A token ending in a dot is an initial group; everything else is surname."""
    surname: list[str] = []
    initials: list[str] = []
    for part in str(name).replace("\xa0", " ").split():
        if part.endswith("."):
            initials.extend(g for g in _ascii(part).split(".") if g)
        else:
            surname.extend(tokens(part))
    return tuple(surname), tuple(initials)


def _find_in_order(hay: tuple[str, ...], needle: tuple[str, ...]) -> tuple[int, ...] | None:
    """Positions in `hay` of the `needle` tokens that occur there, in order
    though not necessarily adjacent. Either side may carry a surname token
    the other drops -- the schedule's "Meligeni Rodrigues Alves F." is
    Polymarket's "Felipe Meligeni Alves" -- so one missing token is
    tolerated, but the last one (the name people actually go by) must be
    present."""
    positions, start = [], 0
    for tok in needle:
        try:
            idx = hay.index(tok, start)
        except ValueError:
            continue
        positions.append(idx)
        start = idx + 1
    if not positions or len(positions) < len(needle) - 1:
        return None
    if needle[-1] not in hay[positions[0]:]:
        return None
    return tuple(positions)


def name_matches(abbreviated: str, full: str) -> bool:
    """Does the schedule's abbreviated name denote the market's full name?"""
    surname, initials = split_abbreviated(abbreviated)
    full_t = tokens(full)
    if not surname or not full_t:
        return False
    used = _find_in_order(full_t, surname)
    if used is None:
        return False
    if not initials:
        return True
    rest = [t for i, t in enumerate(full_t) if i not in used]
    if not rest:
        return True
    return any(t.startswith(initials[0]) for t in rest)


def pair_orientation(abbrev_1: str, abbrev_2: str, full_a: str, full_b: str) -> bool | None:
    """True if (abbrev_1, abbrev_2) is (full_a, full_b), False if reversed,
    None when the pairing is ambiguous or does not hold."""
    one_a, one_b = name_matches(abbrev_1, full_a), name_matches(abbrev_1, full_b)
    two_a, two_b = name_matches(abbrev_2, full_a), name_matches(abbrev_2, full_b)
    if one_a and two_b and not (one_b or two_a):
        return True
    if one_b and two_a and not (one_a or two_b):
        return False
    return None


def _as_date(value) -> dt.date | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


def attach_markets(sched: pd.DataFrame, markets: pd.DataFrame,
                   max_day_gap: int = 1) -> dict[str, list[dict]]:
    """{schedule match_id -> [market row + 'first_is_player1']}.

    A market row is attached when both schedule names resolve onto its two
    players and the dates lie within `max_day_gap` days of each other (the
    schedule day is the local playing day, the market's is UTC)."""
    out: dict[str, list[dict]] = {}
    if markets is None or markets.empty or sched is None or sched.empty:
        return out
    rows = markets.to_dict("records")
    for r in rows:
        r["_date"] = _as_date(r.get("match_date"))
    for m in sched.itertuples(index=False):
        m_date = _as_date(getattr(m, "date", None))
        hits = []
        for r in rows:
            if m_date and r["_date"] and abs((r["_date"] - m_date).days) > max_day_gap:
                continue
            orient = pair_orientation(str(m.player1), str(m.player2),
                                      str(r["player_a"]), str(r["player_b"]))
            if orient is None:
                continue
            hit = {k: v for k, v in r.items() if k != "_date"}
            hit["first_is_player1"] = orient
            hits.append(hit)
        if hits:
            out[str(m.match_id)] = hits
    return out


# ------------------------------------------------------------- quotes ----

def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def market_quote(row: dict, first_is_player1: bool) -> dict:
    """A prediction-market row oriented onto (player1, player2)."""
    ask = [_f(row.get("ask_a")), _f(row.get("ask_b"))]
    bid = [_f(row.get("bid_a")), _f(row.get("bid_b"))]
    if not first_is_player1:
        ask, bid = ask[::-1], bid[::-1]
    fee = _f(row.get("fee_rate")) or 0.0
    maker_fee = _f(row.get("maker_fee_rate")) or 0.0
    mid = [None, None]
    for i in range(2):
        if ask[i] is not None and bid[i] is not None:
            mid[i] = (ask[i] + bid[i]) / 2.0
    return {
        "venue": str(row.get("venue")),
        "ask": ask, "bid": bid, "mid": mid,
        "fee_rate": fee, "maker_fee_rate": maker_fee,
        # What a taker gets, fee included.
        "taker_odds": [effective_odds(p, fee) for p in ask],
        # What a resting order at the current best bid would get if filled.
        "maker_odds": [effective_odds(p, maker_fee) for p in bid],
        "liquidity": _f(row.get("liquidity")),
        "volume": _f(row.get("volume")),
        "start_time": row.get("start_time") if isinstance(row.get("start_time"), pd.Timestamp) else None,
        "url": row.get("url"),
    }


# A liquid prediction market is a two-sided order book a cent or two wide,
# so its mid needs no de-vigging. Measured on the first card that carried
# both (2026-10-22, 24 liquid sides): the mids sat 0.59 percentage points
# from Pinnacle's de-vigged price on average -- the same distance a soft
# book's de-vigged price keeps (0.63 at the median over 20 000 historical
# matches), without the soft book's margin shape. Where TennisExplorer has no
# sharp book for a match, that mid is the better fair value.
EXCHANGE_MIN_LIQUIDITY = 5000.0
EXCHANGE_MAX_SPREAD = 0.02


def exchange_anchor(markets: list[dict], min_liquidity: float = EXCHANGE_MIN_LIQUIDITY,
                    max_spread: float = EXCHANGE_MAX_SPREAD) -> dict | None:
    """The most liquid prediction-market quote tight enough to serve as a
    fair value: {venue, fair, liquidity, spread}, or None."""
    best = None
    for q in markets or []:
        mid = q.get("mid") or [None, None]
        ask, bid = q.get("ask") or [None, None], q.get("bid") or [None, None]
        liq = q.get("liquidity") or 0.0
        if None in mid or None in ask or None in bid or liq < min_liquidity:
            continue
        spread = max(ask[0] - bid[0], ask[1] - bid[1])
        if spread > max_spread or mid[0] + mid[1] <= 0:
            continue
        total = mid[0] + mid[1]
        cand = {"venue": q["venue"], "fair": (mid[0] / total, mid[1] / total),
                "liquidity": liq, "spread": round(spread, 4)}
        if best is None or liq > best["liquidity"]:
            best = cand
    return best


def value_rows(players, fair, books: dict, markets: list[dict],
               ref_book: str | None = None) -> list[dict]:
    """Every priced side at every venue, with its EV against `fair`.

    `books` is {bookmaker -> [odds_1, odds_2]} oriented onto `players`;
    `markets` is a list from `market_quote`."""
    rows = []
    for book, odds in (books or {}).items():
        for i in range(2):
            price = _f(odds[i]) if odds and len(odds) == 2 else None
            if price is None or price <= 1.0:
                continue
            rows.append({
                "player": players[i], "venue": book, "kind": "book",
                "odds": round(price, 3), "fair_prob": round(fair[i], 4),
                "ev": round(fair[i] * price - 1.0, 4),
                "is_sharp": book in SHARP_BOOKS, "is_reference": book == ref_book,
                "signal_only": book in SIGNAL_ONLY_VENUES,
            })
    for q in markets or []:
        for i in range(2):
            if q["taker_odds"][i] is None and q["maker_odds"][i] is None:
                continue
            rows.append({
                "player": players[i], "venue": q["venue"], "kind": "prediction",
                "ask": q["ask"][i], "bid": q["bid"][i], "mid": q["mid"][i],
                "odds": round(q["taker_odds"][i], 3) if q["taker_odds"][i] else None,
                "maker_odds": round(q["maker_odds"][i], 3) if q["maker_odds"][i] else None,
                "fair_prob": round(fair[i], 4),
                "ev": (round(fair[i] * q["taker_odds"][i] - 1.0, 4)
                       if q["taker_odds"][i] else None),
                "ev_maker": (round(fair[i] * q["maker_odds"][i] - 1.0, 4)
                             if q["maker_odds"][i] else None),
                # How far the market's mid sits from the sharp fair value --
                # the disagreement itself, before any fee.
                "mid_gap": (round(q["mid"][i] - fair[i], 4) if q["mid"][i] is not None else None),
                "liquidity": q["liquidity"], "url": q.get("url"),
                "is_sharp": False, "is_reference": False, "signal_only": True,
            })
    return rows


def best_arbitrage(players, books: dict, markets: list[dict]) -> dict | None:
    """Best price per side over all venues, and whether the pair pays out
    more than it costs. Prediction-market prices enter fee-included."""
    best = [None, None]

    def offer(i, venue, odds, signal_only):
        o = _f(odds)
        if o is None or o <= 1.0:
            return
        if best[i] is None or o > best[i]["odds"]:
            best[i] = {"venue": venue, "odds": round(o, 3), "signal_only": signal_only}

    for book, odds in (books or {}).items():
        if book in UNNAMED_VENUES or not odds or len(odds) != 2:
            continue
        for i in range(2):
            offer(i, book, odds[i], book in SIGNAL_ONLY_VENUES)
    for q in markets or []:
        for i in range(2):
            offer(i, q["venue"], q["taker_odds"][i], True)
    if best[0] is None or best[1] is None:
        return None
    total = 1.0 / best[0]["odds"] + 1.0 / best[1]["odds"]
    margin = total - 1.0
    return {
        "side_a": {"player": players[0], **best[0]},
        "side_b": {"player": players[1], **best[1]},
        "margin": round(margin, 4),
        "profit": round(1.0 / total - 1.0, 4),
        # Stake shares that make both outcomes pay the same.
        "stake_a": round((1.0 / best[0]["odds"]) / total, 4),
        "stake_b": round((1.0 / best[1]["odds"]) / total, 4),
        "is_arbitrage": margin < 0,
        "signal_only": best[0]["signal_only"] or best[1]["signal_only"],
    }


# ---------------------------------------------------------- snapshots ----

SNAPSHOT_COLUMNS = ["taken_at", "match_id", "date", "start_time", "tournament", "player1",
                    "player2", "venue", "kind", "odds1", "odds2", "liquidity"]


def snapshot_rows(match: dict, taken_at: str) -> list[dict]:
    """One row per venue quoting the match: the raw material for the
    opening-vs-closing study and for closing-line value."""
    players = match.get("players") or [s["player"] for s in match["sides"]]
    base = {"taken_at": taken_at, "match_id": match.get("match_id"),
            "date": match.get("date"), "start_time": match.get("start_time"),
            "tournament": match.get("tournament"),
            "player1": players[0], "player2": players[1]}
    rows = []
    for book, odds in (match.get("books") or {}).items():
        rows.append({**base, "venue": book, "kind": "book",
                     "odds1": odds[0], "odds2": odds[1], "liquidity": None})
    for q in match.get("prediction_markets") or []:
        rows.append({**base, "venue": q["venue"], "kind": "prediction",
                     "odds1": q["taker_odds"][0], "odds2": q["taker_odds"][1],
                     "liquidity": q.get("liquidity")})
    return rows


def append_snapshots(path: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)
    path = Path(path)
    header = not path.exists() or path.stat().st_size == 0
    df.to_csv(path, mode="a", header=header, index=False)
    return len(df)


def load_snapshots(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    df = pd.read_csv(path, dtype={"match_id": str})
    df["taken_at"] = pd.to_datetime(df["taken_at"], utc=True, errors="coerce")
    return df


def opening_and_closing(snapshots: pd.DataFrame, venue: str = "Pinnacle") -> pd.DataFrame:
    """First and last recorded quote per match for one venue."""
    if snapshots.empty:
        return pd.DataFrame()
    v = snapshots[snapshots["venue"] == venue].sort_values("taken_at")
    first = v.groupby("match_id").first()
    last = v.groupby("match_id").last()
    out = first[["date", "start_time", "tournament", "player1", "player2"]].copy()
    out["open1"], out["open2"] = first["odds1"], first["odds2"]
    out["close1"], out["close2"] = last["odds1"], last["odds2"]
    out["opened_at"], out["closed_at"] = first["taken_at"], last["taken_at"]
    out["n_snapshots"] = v.groupby("match_id").size()
    return out.reset_index()


def closing_value(odds_taken: float, closing_pair: list[float]) -> float | None:
    """CLV: the price taken against the closing de-vigged probability of the
    same side. Positive means the market moved towards the pick."""
    if not closing_pair or any(x is None or x <= 1.0 for x in closing_pair):
        return None
    fair = odds_math.shin_devig(list(closing_pair))
    return odds_taken * fair[0] - 1.0
