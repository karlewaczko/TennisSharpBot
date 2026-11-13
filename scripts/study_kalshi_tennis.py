#!/usr/bin/env python3
"""Tennis: in a big pre-match move, does Kalshi or Polymarket move first?

    python scripts/study_kalshi_tennis.py --days 6

Every ATP and WTA match of the last `--days` days that both venues listed:
Polymarket's minute prices and Kalshi's minute candles (the middle of bid
and ask) for the same player. A move (3+ points within 30 minutes, held three
hours on) found on either venue is timed on both, where each crossed half
way. bet365, Pinnacle and Betfair against Polymarket come from
scripts/study_pm_leadlag.py (TennisExplorer).

Results go to data/reports/kalshi_vs_polymarket_tennis.json.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from tennissharp import config
from tennissharp import market_compare as mc


def _load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


so, ll = _load("study_stale_odds"), _load("study_pm_leadlag")
OUT = config.REPORTS_DIR / "kalshi_vs_polymarket_tennis.json"
SERIES = ("KXATPMATCH", "KXWTAMATCH")


def kalshi_matches(days: int, now: pd.Timestamp) -> list[dict]:
    """Kalshi's settled tennis matches: the day, both players and their markets."""
    out = []
    for series in SERIES:
        cursor, events = None, {}
        for _ in range(20):
            params = {"series_ticker": series, "status": "settled", "limit": 1000,
                      "min_close_ts": int((now - pd.Timedelta(days=days + 1)).timestamp())}
            if cursor:
                params["cursor"] = cursor
            r = so._get(f"{so.KALSHI}/markets", params, pause=so.KALSHI_PAUSE)
            js = r.json() if r is not None else {}
            for m in js.get("markets", []):
                events.setdefault(m.get("event_ticker"), []).append({**m, "series": series})
            cursor = js.get("cursor")
            if not cursor:
                break
        for ticker, ms in events.items():
            if len(ms) == 2:
                day = so._kalshi_day(str(ticker).split("-", 1)[-1])
                out.append({"day": day, "markets": ms, "players": [str(m.get("yes_sub_title") or "") for m in ms]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=6)
    ap.add_argument("--jump", type=float, default=0.03)
    ap.add_argument("--min-volume", type=float, default=5000.0)
    args = ap.parse_args()
    now = pd.Timestamp.now(tz="UTC")
    pm, ks = ll.markets(args.days, args.min_volume, now), kalshi_matches(args.days, now)
    print(f"Polymarket tennis moneylines: {len(pm)} | Kalshi tennis matches: {len(ks)}", flush=True)
    pairs, both = [], 0
    for m in pm:
        if len(m["outcomes"]) != 2 or len(m["tokens"]) != 2:
            continue
        day = m["gst"].tz_convert(so.CLOCK).normalize()
        a, b = m["outcomes"]
        k = next((k for k in ks if k["day"] is not None and abs((k["day"] - day).days) <= 1
                  and any(mc.name_matches(a, p) for p in k["players"]) and any(mc.name_matches(b, p) for p in k["players"])), None)
        if k is None:
            continue
        km = next((x for x in k["markets"] if mc.name_matches(a, str(x.get("yes_sub_title") or ""))), None)
        if km is None:
            continue
        cut = m["gst"] - pd.Timedelta(minutes=2)
        P = so.on_grid(so.pm_history(m["tokens"][0], m["gst"]), cut)
        K = so.on_grid(so.kalshi_history(km, m["gst"]), cut)
        if P is None or K is None:
            continue
        both += 1
        for who, S in (("Polymarket", P), ("Kalshi", K)):
            for x in so.moves(S, args.jump):
                t_p = so.crossing(P, x["t0"], x["t1"], x["sgn"], args.jump / 2)
                t_k = so.crossing(K, x["t0"], x["t1"], x["sgn"], args.jump / 2)
                if t_p is not None and t_k is not None:
                    pairs.append({"slug": m["slug"], "found_in": who, "t": x["t_x"].isoformat(),
                                  "kalshi_after_polymarket_min": round((t_k - t_p).total_seconds() / 60, 1)})
    seen, uniq = set(), []                      # a move found on both venues counts once
    for p in pairs:
        key = (p["slug"], round(pd.Timestamp(p["t"]).timestamp() / 3600))
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    report = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "days": args.days,
              "jump": args.jump, "matches_on_both": both, "kalshi_vs_polymarket": so.lead(uniq), "moves": uniq}
    OUT.write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: report[k] for k in ("matches_on_both", "kalshi_vs_polymarket")}, indent=1))


if __name__ == "__main__":
    main()
