#!/usr/bin/env python3
"""Rank Polymarket's tennis traders and measure how sharp its closing
prices are.

    python scripts/update_pm_traders.py --days 30

Writes data/processed/pm_tennis_traders.csv (the ranked wallets) and
data/reports/prediction_market_sharpness.json: the calibration of
Polymarket's pre-match closing prices on the same closed markets, and --
from data/processed/pm_gap_log.csv, which every dashboard run extends --
how far Polymarket's and Kalshi's mid prices sit from Pinnacle's and
Betfair's de-vigged price. Runs weekly in GitHub Actions; see
tennissharp/data/polymarket_traders.py for the method.
"""
import _bootstrap  # noqa: F401
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import datetime as dt
import json
import logging
import time

import pandas as pd

from tennissharp import config
from tennissharp.data import polymarket_traders as pt

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def gap_summary(path) -> dict:
    """Distance of prediction-market mids from the sharp fair value."""
    try:
        g = pd.read_csv(path)
    except (OSError, ValueError):
        return {}
    if g.empty:
        return {}
    g = g.drop_duplicates(subset=["taken_at", "match_id", "venue", "player"])
    g["abs_gap"] = (g["mid"] - g["fair"]).abs()
    out = {}
    for venue, v in g.groupby("venue"):
        liquid = v[v["liquidity"].fillna(0) >= 5000]
        out[venue] = {"sides": int(len(v)), "matches": int(v["match_id"].nunique()),
                      "median_gap_pp": round(float(v["abs_gap"].median() * 100), 2),
                      "mean_gap_pp": round(float(v["abs_gap"].mean() * 100), 2),
                      "share_within_1pp": round(float((v["abs_gap"] <= 0.01).mean()), 3),
                      "liquid_median_gap_pp": (round(float(liquid["abs_gap"].median() * 100), 2)
                                               if len(liquid) else None),
                      "median_spread_c": (round(float(v["spread"].median() * 100), 2)
                                          if "spread" in v and v["spread"].notna().any() else None)}
    out["first_logged"] = str(g["taken_at"].min())
    out["last_logged"] = str(g["taken_at"].max())
    return out


DEFAULT_MIN_VOLUME = {"tennis": 1000.0, "soccer": 10000.0, "basketball": 5000.0}
WORKERS = 3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", choices=sorted(pt.SPORT_TAGS), default="tennis")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--tours", default="atp,wta", help="tennis only: the circuits to rank")
    ap.add_argument("--min-volume", type=float,
                    help="skip markets that traded less than this many dollars "
                         "(default 1000 tennis, 10000 football, 5000 basketball)")
    ap.add_argument("--per-market-out", type=Path,
                    help="also write every wallet-market row there (large; for analysis)")
    args = ap.parse_args()
    tours = (tuple(t.strip() for t in args.tours.split(",") if t.strip())
             if args.sport == "tennis" else None)
    min_volume = DEFAULT_MIN_VOLUME[args.sport] if args.min_volume is None else args.min_volume

    t0 = time.time()
    markets = pt.closed_markets(days=args.days, tours=tours, sport=args.sport, min_volume=min_volume)
    logger.info("Closed %s moneylines in window: %d", args.sport, len(markets))
    per_market, mrows = [], []

    def work(m):
        trades, floor, takers = pt.market_trades(m["condition_id"])
        close_a, rows = pt.account_market(trades, m["winner"], m["start_ts"], m.get("fee_rate", 0.0), takers)
        return m, close_a, rows, len(trades), floor, len(takers)

    # Three markets at a time: the run takes a third as long and stays well
    # inside the API's rate limits (it backs off on 429 anyway).
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(work, m) for m in markets]
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                m, close_a, rows, n_trades, floor, n_takers = fut.result()
            except Exception as exc:
                logger.warning("trades failed: %s", exc)
                continue
            mrows.append({**m, "close_a": close_a, "trades": n_trades, "taker_fills": n_takers,
                          "min_trade_usd": floor})
            for r in rows:
                per_market.append({**r, "slug": m["slug"]})
            if i % 100 == 0:
                logger.info("  %d/%d markets, %.0fs", i, len(markets), time.time() - t0)

    pm = pd.DataFrame(per_market)
    if args.per_market_out:
        pm.to_csv(args.per_market_out, index=False)
        pd.DataFrame(mrows).to_csv(args.per_market_out.with_suffix(".markets.csv"), index=False)
    lb, report = write_outputs(pm, pd.DataFrame(mrows), args.days, tours, args.sport)
    print(json.dumps({k: v for k, v in report.items() if k != "leader_preview"}, indent=1, default=str))
    print(lb.head(15).round(3).to_string(index=False))


def write_outputs(pm: pd.DataFrame, mk: pd.DataFrame, days: int, tours,
                  sport: str = "tennis") -> tuple[pd.DataFrame, dict]:
    """The ranking (pm_<sport>_traders.csv) and its report: for tennis
    prediction_market_sharpness.json, with the gap to the sharp books that
    the dashboard logs; otherwise pm_<sport>_traders.json."""
    ev = pt.by_event(pm)
    lb = pt.leaderboard(ev)
    lb.to_csv(config.PROCESSED_DIR / f"pm_{sport}_traders.csv", index=False)
    # Every wallet's CLV in this sport, ranked or not, so the live page can
    # show a watched account's figure in each sport. Regenerated each run,
    # under data/raw and not committed.
    stats = pt.wallet_table(ev)
    stats = stats[stats["pre_markets"] >= pt.STATS_MIN_PRE_MARKETS]
    cache = config.RAW_DIR / "pm"
    cache.mkdir(parents=True, exist_ok=True)
    stats.round(4).to_csv(cache / f"pm_{sport}_wallet_stats.csv", index=False)
    report = {
        "measured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sport": sport, "window_days": days, "tours": list(tours) if tours else None,
        "markets": int(len(mk)), "matches": int(mk["slug"].nunique()) if len(mk) else 0,
        "wallets": int(pm["wallet"].nunique()) if len(pm) else 0,
        "ranked_wallets": int(len(lb)),
        "markets_trimmed_to_bigger_trades": (int((mk["min_trade_usd"] > 0).sum())
                                             if "min_trade_usd" in mk.columns else 0),
        "market_structure": pt.market_structure(ev),
        "skill_persistence": pt.persistence(ev, mk),
        "polymarket_closing_calibration": pt.calibration(mk) if len(mk) else {"n": 0},
        "leader_preview": lb.head(10).round(4).to_dict("records"),
    }
    if sport == "tennis":
        report["gap_to_sharp"] = gap_summary(config.PROCESSED_DIR / "pm_gap_log.csv")
        path = config.REPORTS_DIR / "prediction_market_sharpness.json"
    else:
        path = config.REPORTS_DIR / f"pm_{sport}_traders.json"
    path.write_text(json.dumps(report, indent=1, default=str))
    return lb, report

if __name__ == "__main__":
    main()
