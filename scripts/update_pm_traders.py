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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--tours", default="atp,wta")
    ap.add_argument("--min-volume", type=float, default=1000.0,
                    help="skip markets that traded less than this many dollars")
    ap.add_argument("--per-market-out", type=Path,
                    help="also write every wallet-market row there (large; for analysis)")
    args = ap.parse_args()
    tours = tuple(t.strip() for t in args.tours.split(",") if t.strip())

    t0 = time.time()
    markets = pt.closed_markets(days=args.days, tours=tours, min_volume=args.min_volume)
    logger.info("Closed tennis moneylines in window: %d", len(markets))
    per_market, mrows = [], []
    for i, m in enumerate(markets, 1):
        try:
            trades = pt.market_trades(m["condition_id"])
        except Exception as exc:
            logger.warning("trades for %s failed: %s", m["slug"], exc)
            continue
        close_a, rows = pt.account_market(trades, m["winner"], m["start_ts"])
        mrows.append({**m, "close_a": close_a, "trades": len(trades)})
        for r in rows:
            per_market.append({**r, "slug": m["slug"]})
        if i % 100 == 0:
            logger.info("  %d/%d markets, %.0fs", i, len(markets), time.time() - t0)
        time.sleep(pt.PAUSE)

    pm = pd.DataFrame(per_market)
    if args.per_market_out:
        pm.to_csv(args.per_market_out, index=False)
        pd.DataFrame(mrows).to_csv(args.per_market_out.with_suffix(".markets.csv"), index=False)
    lb = pt.leaderboard(pm)
    lb.to_csv(config.PROCESSED_DIR / "pm_tennis_traders.csv", index=False)
    mk = pd.DataFrame(mrows)
    report = {
        "measured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "window_days": args.days, "tours": list(tours),
        "markets": int(len(mk)), "wallets": int(pm["wallet"].nunique()) if len(pm) else 0,
        "ranked_wallets": int(len(lb)),
        "polymarket_closing_calibration": pt.calibration(mk) if len(mk) else {"n": 0},
        "gap_to_sharp": gap_summary(config.PROCESSED_DIR / "pm_gap_log.csv"),
        "leader_preview": lb.head(10).round(4).to_dict("records"),
    }
    (config.REPORTS_DIR / "prediction_market_sharpness.json").write_text(
        json.dumps(report, indent=1, default=str))
    print(json.dumps({k: v for k, v in report.items() if k != "leader_preview"}, indent=1, default=str))
    print(lb.head(15).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
