#!/usr/bin/env python3
"""Big pre-match moves in tennis: does Polymarket move before the bookmakers?

    python scripts/study_pm_leadlag.py --days 6

Every Polymarket tennis moneyline whose match started in the last `--days`
days, with at least `--min-volume` traded, is joined to TennisExplorer's
odds histories. A big move is a price that shifts `--jump` or more within
30 minutes and holds it, in Polymarket's minute prices or in Pinnacle's
recorded ones. For each move the script times when Polymarket, Pinnacle and
every other bookmaker crossed half way from their level an hour before the
move to their level three hours on.

TennisExplorer shapes the method (see the scraper's docstring):
- Its times are Prague time.
- A match keeps its full history for about a week, so `--days` should stay
  under 7.
- Its Pinnacle entries trail the first other bookmaker's by around 20
  minutes in most moves. That is impossible for the book the others copy,
  so the site records Pinnacle late. Polymarket is therefore timed against
  the bookmakers as a group (the first and the median of those that moved),
  and Pinnacle's own time is reported but not trusted.

Results go to data/reports/pm_leadlag.json. The reading is in
data/reports/profi_wetten_und_edge.md, section 4i.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from tennissharp import config
from tennissharp import market_compare as mc
from tennissharp.data import polymarket_traders as pt
from tennissharp.data import tennisexplorer as te

CLOB = "https://clob.polymarket.com/prices-history"
WINDOW = pd.Timedelta(minutes=30)        # a jump: this much move within half an hour
BEFORE, AFTER = pd.Timedelta(minutes=60), pd.Timedelta(minutes=180)
SAME = 5                                 # minutes apart still counted as the same time
PAUSE = 1.5                              # seconds between TennisExplorer requests, per worker
HEADER = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\s*,\s*(\d{2}):(\d{2})")
OUT = config.REPORTS_DIR / "pm_leadlag.json"


def markets(days: int, min_volume: float, now: pd.Timestamp) -> list[dict]:
    """Tennis moneylines, open or settled, whose match started in the window."""
    out, seen = [], set()
    day, end = now - pd.Timedelta(days=days + 1), now + pd.Timedelta(days=8)   # endDate can be start + 7 days
    while day < end:
        nxt = day + pd.Timedelta(days=1)
        for closed in ("true", "false"):
            for off in range(0, 3000, 100):
                rows = _gamma({"tag_id": pt.SPORT_TAGS["tennis"][0], "closed": closed, "sports_market_types": "moneyline", "limit": 100,
                               "offset": off, "end_date_min": pt._iso(day.timestamp()), "end_date_max": pt._iso(nxt.timestamp())})
                for m in rows:
                    start = pt._ts(m.get("gameStartTime"))
                    if m["conditionId"] in seen or start is None or float(m.get("volumeNum") or 0) < min_volume:
                        continue
                    seen.add(m["conditionId"])
                    start = pd.Timestamp(start, unit="s", tz="UTC")
                    if now - pd.Timedelta(days=days) <= start <= now - pd.Timedelta(hours=1):
                        out.append({"slug": m["slug"], "outcomes": pt._json_list(m["outcomes"]),
                                    "tokens": pt._json_list(m["clobTokenIds"]), "gst": start, "volume": float(m["volumeNum"])})
                if len(rows) < 100:
                    break
        day = nxt
    return out


def _gamma(params: dict) -> list:
    """One page of markets; an error answer (Gamma sends a JSON object then) is retried, then read as empty."""
    for attempt in range(3):
        rows = requests.get(f"{pt.GAMMA_API}/markets", params=params, timeout=30).json()
        if isinstance(rows, list):
            return rows
        time.sleep(2 * (attempt + 1))
    return []


def schedule(days: int) -> pd.DataFrame:
    pages = []
    for off in range(-days - 1, 1):
        pages.append(te.fetch_matches(off))
        time.sleep(2.0)
    s = pd.concat(pages, ignore_index=True)
    s = s[s.match_id.notna()].copy()
    s["start"] = pd.to_datetime(s["date"] + " " + s["time"].fillna("00:00"), format="%Y-%m-%d %H:%M", errors="coerce", utc=True)
    return s


def join(pm: list[dict], sched: pd.DataFrame) -> list[dict]:
    """Each market with its TennisExplorer match, outcomes put in the schedule's order."""
    jobs = []
    for m in pm:
        near = sched[(sched.start - m["gst"]).abs() < pd.Timedelta(hours=30)]
        best = None
        for _, r in near.iterrows():
            same = mc.pair_orientation(r.player1, r.player2, *m["outcomes"])
            if same is not None and (best is None or abs(r.start - m["gst"]) < abs(best[0].start - m["gst"])):
                best = (r, same)
        if best:
            r, same = best
            jobs.append({**m, "match_id": str(r.match_id), "players": [r.player1, r.player2], "tournament": r.tournament,
                         "token": m["tokens"][0 if same else 1]})
    return jobs


def fetch(job: dict) -> dict | None:
    """TennisExplorer's history (UTC) and Polymarket's minute prices for the schedule's first player."""
    time.sleep(PAUSE)
    html = requests.get(f"{te.BASE_URL}/match-detail/?id={job['match_id']}&timezone=0", headers=te._HEADERS, timeout=30).text
    hist = te.parse_odds_history_html(html, reference_date=job["gst"].date())
    if hist.empty or "Pinnacle" not in set(hist.bookmaker):
        return None
    # the history spells names out in full ("Surname Firstname"): map them to the schedule's two
    names = list(dict.fromkeys(hist.player))
    first = [n for n in names if mc.name_matches(job["players"][0], n) and not mc.name_matches(job["players"][1], n)]
    if len(names) != 2 or len(first) != 1:
        return None
    hist = hist.assign(t=te.odds_times_utc(hist.timestamp), first=hist.player == first[0]).dropna(subset=["t"])
    head = HEADER.search(html, max(html.find('id="center"'), 0))           # the actual start, in UTC with timezone=0
    actual = pd.Timestamp(f"{head[3]}-{head[2]}-{head[1]} {head[4]}:{head[5]}", tz="UTC") if head else job["gst"]
    start = min(actual, job["gst"])
    ph = requests.get(CLOB, timeout=30, params={"market": job["token"], "fidelity": 1,
                                                "startTs": int((start - pd.Timedelta(hours=36)).timestamp()), "endTs": int(start.timestamp())}).json()
    pts = ph.get("history", []) if isinstance(ph, dict) else []
    if len(pts) < 60:
        return None
    pm = pd.Series({pd.Timestamp(int(x["t"]), unit="s", tz="UTC"): float(x["p"]) for x in pts}).sort_index()
    return {**job, "hist": hist, "start": start, "pm": pm}


def devig(hist: pd.DataFrame, book: str, cut: pd.Timestamp) -> tuple[pd.Series, pd.DataFrame] | None:
    """The first player's fair chance at each recorded change, and the odds behind it."""
    b = hist[(hist.bookmaker == book) & (hist.t < cut)]
    w = b.pivot_table(index="t", columns="first", values="odds", aggfunc="last").sort_index().ffill().dropna()
    if w.shape[1] != 2 or w.empty:
        return None
    inv = 1 / w
    return inv[True] / (inv[True] + inv[False]), w


def first_jumps(x: pd.Series, jump: float) -> list[tuple[pd.Timestamp, int]]:
    """On a minute grid: the first minute of each move of `jump` within 30 minutes, one per 3 hours."""
    d = (x - x.shift(freq=WINDOW).reindex(x.index)).dropna()
    out, last = [], None
    for t, v in d[d.abs() >= jump].items():
        if last is None or t - last > pd.Timedelta(hours=3):
            out.append((t, int(np.sign(v))))
            last = t
    return out


def crossing(s: pd.Series, t0, t1, sgn: int, least: float):
    """When `s` first stood half way between its level at t0 and at t1, if it moved `least` that way."""
    pre, post = s[s.index <= t0], s[s.index <= t1]
    if pre.empty or post.empty or (post.iloc[-1] - pre.iloc[-1]) * sgn < least:
        return None
    mid, w = (pre.iloc[-1] + post.iloc[-1]) / 2, s[(s.index > t0) & (s.index <= t1)]
    hit = w[(w - mid) * sgn >= 0]
    return hit.index[0] if len(hit) else None


def level(s: pd.Series, t):
    s = s[s.index <= t]
    return float(s.iloc[-1]) if len(s) else np.nan


def events(m: dict, jump: float) -> list[dict]:
    cut = m["start"] - pd.Timedelta(minutes=2)
    pin = devig(m["hist"], "Pinnacle", cut)
    if pin is None:
        return []
    q, pin_odds = pin
    pm = m["pm"][m["pm"].index < cut]
    grid = pd.date_range(max(q.index[0], pm.index[0]).ceil("min"), cut.floor("min"), freq="min")
    if len(grid) < 120:
        return []
    P = pm.reindex(pm.index.union(grid)).ffill().reindex(grid)
    Q = q.reindex(q.index.union(grid)).ffill().reindex(grid)
    books = {b: devig(m["hist"], b, cut) for b in set(m["hist"].bookmaker) - {"Pinnacle"}}
    books = {b: v for b, v in books.items() if v is not None}
    found = sorted([(t, s, "Polymarket") for t, s in first_jumps(P, jump)] + [(t, s, "Pinnacle") for t, s in first_jumps(Q, jump)])
    out, taken = [], []
    for t, sgn, where in found:
        if any(abs(t - u) < pd.Timedelta(hours=3) for u in taken):
            continue
        t0, t1 = t - BEFORE, min(t + AFTER, cut)
        if t0 < grid[0] or t1 - t < WINDOW:
            continue
        held = (P[t1] - P[t0]) * sgn if where == "Polymarket" else (Q[t1] - Q[t0]) * sgn
        if held < jump:
            continue
        taken.append(t)
        t_pm, t_pin = crossing(P, t0, t1, sgn, jump / 2), crossing(q, t0, t1, sgn, jump / 2)
        t_books = {b: c for b, (s, _) in books.items() if (c := crossing(s, t0, t1, sgn, jump / 2)) is not None}
        # value of the price still on offer a minute after Polymarket crossed, at Pinnacle's own closing fair price
        stale = {}
        if t_pm is not None:
            at, fair = t_pm + pd.Timedelta(minutes=1), q.iloc[-1] if sgn > 0 else 1 - q.iloc[-1]
            for b, odds in [("Pinnacle", pin_odds)] + [(b, w) for b, (_, w) in books.items()]:
                o = level(odds[sgn > 0], at)
                if not np.isnan(o):
                    stale[b] = fair * o - 1
        out.append({"slug": m["slug"], "t": t, "found_in": where, "sgn": sgn, "volume": m["volume"],
                    "pm_move": (P[t1] - P[t0]) * sgn, "pin_move": (Q[t1] - Q[t0]) * sgn,
                    "pm_kept_to_close": (P.iloc[-1] - P[t0]) * sgn >= jump / 2,
                    "t_pm": t_pm, "t_pin": t_pin, "t_books": t_books, "stale": stale})
    return out


def minutes(a, b) -> float:
    return (a - b).total_seconds() / 60


def order(lags: list[float]) -> dict:
    """Lags in minutes, positive when Polymarket came first."""
    x = np.array(lags, dtype=float)
    if not len(x):
        return {"n": 0}
    return {"n": int(len(x)), "median_min": round(float(np.median(x)), 1), "pm_first": round(float(np.mean(x > SAME)), 3),
            "same_time": round(float(np.mean(np.abs(x) <= SAME)), 3), "pm_later": round(float(np.mean(x < -SAME)), 3)}


def summarize(ev: list[dict], matches: int, args) -> dict:
    vs_first, vs_median, pin_vs_first, vs_pin, lag_by_book, stale_by_book = [], [], [], [], {}, {}
    alone = [e for e in ev if e["t_pm"] is not None and not e["t_books"] and e["t_pin"] is None]
    for e in ev:
        books = sorted(e["t_books"].values())
        if e["t_pm"] is not None and books:
            vs_first.append(minutes(books[0], e["t_pm"]))
            vs_median.append(minutes(books[len(books) // 2], e["t_pm"]))
        if e["t_pin"] is not None and books:
            pin_vs_first.append(minutes(e["t_pin"], books[0]))
        if e["t_pm"] is not None and e["t_pin"] is not None:
            vs_pin.append(minutes(e["t_pin"], e["t_pm"]))
        if e["t_pm"] is not None:
            for b, t in [*e["t_books"].items(), ("Pinnacle", e["t_pin"])]:
                if t is not None:
                    lag_by_book.setdefault(b, []).append(minutes(t, e["t_pm"]))
            for b, v in e["stale"].items():
                stale_by_book.setdefault(b, []).append(v)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "days": args.days, "jump": args.jump, "min_volume": args.min_volume, "matches": matches, "moves": len(ev),
        "moved_in": {"polymarket_and_books": sum(1 for e in ev if e["t_pm"] is not None and (e["t_books"] or e["t_pin"] is not None)),
                     "polymarket_alone": len(alone),
                     "books_alone": sum(1 for e in ev if e["t_pm"] is None)},
        "polymarket_vs_first_bookmaker": order(vs_first),
        "polymarket_vs_median_bookmaker": order(vs_median),
        "polymarket_vs_pinnacle_as_recorded": order(vs_pin),
        "pinnacle_as_recorded_after_first_bookmaker": {"n": len(pin_vs_first), "median_min": round(float(np.median(pin_vs_first)), 1) if pin_vs_first else None,
                                                       "later_than_5_min": round(float(np.mean(np.array(pin_vs_first) > SAME)), 3) if pin_vs_first else None},
        "minutes_after_polymarket_by_book": {b: {"n": len(v), "median": round(float(np.median(v)), 1)}
                                             for b, v in sorted(lag_by_book.items(), key=lambda kv: np.median(kv[1])) if len(v) >= 5},
        "stale_price_value_vs_pinnacle_close": {b: {"n": len(v), "mean": round(float(np.mean(v)), 4), "median": round(float(np.median(v)), 4)}
                                                for b, v in sorted(stale_by_book.items(), key=lambda kv: -np.mean(kv[1])) if len(v) >= 5},
        "polymarket_alone_kept_to_start": round(float(np.mean([e["pm_kept_to_close"] for e in alone])), 3) if alone else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=6, help="matches started in the last N days (TennisExplorer keeps full histories about a week)")
    ap.add_argument("--jump", type=float, default=0.03, help="a big move: this much within 30 minutes")
    ap.add_argument("--min-volume", type=float, default=2000, help="Polymarket volume floor in dollars")
    args = ap.parse_args()
    now = pd.Timestamp.now(tz="UTC")
    pm = markets(args.days, args.min_volume, now)
    jobs = join(pm, schedule(args.days))
    print(f"Polymarket tennis moneylines: {len(pm)} | on TennisExplorer: {len(jobs)}", flush=True)
    with ThreadPoolExecutor(2) as ex:
        data = [m for m in ex.map(lambda j: _safe(fetch, j), jobs) if m]
    ev = [e for m in data for e in events(m, args.jump)]
    out = summarize(ev, len(data), args)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _safe(fn, arg):
    try:
        return fn(arg)
    except (requests.RequestException, ValueError, KeyError):
        return None


if __name__ == "__main__":
    main()
