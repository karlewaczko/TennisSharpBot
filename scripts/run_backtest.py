#!/usr/bin/env python3
"""Simulate the value-betting strategy over historical data and report ROI.

Reminder: a positive backtest ROI on historical odds is a *necessary*, not
sufficient, condition for real profitability -- it doesn't account for bet
limits/limiting by bookmakers, odds moving between your decision and your
bet being placed, or the fact this model has never seen live markets.

Before trusting anything here, run scripts/audit_edge.py, which tests whether
an edge is even possible with this data.
"""
import _bootstrap  # noqa: F401
import argparse
import json

import pandas as pd

from tennissharp import config, edge_audit
from tennissharp.backtest import run_backtest
from tennissharp.data import odds_history
from tennissharp.tourney_matching import load_surface_speed_index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--edge-threshold", type=float, default=0.10)
    parser.add_argument("--kelly-fraction", type=float, default=0.25)
    parser.add_argument("--bankroll", type=float, default=10_000.0)
    parser.add_argument("--min-train-seasons", type=int, default=5)
    parser.add_argument("--bet-at", default="market_avg",
                        help="Book to place bets at (must be an attainable price)")
    parser.add_argument("--priced-against", default="pinnacle",
                        help="Sharp book used as the model's reference price")
    parser.add_argument("--no-market", action="store_true",
                        help="Train without the market price (worse forecasts; for comparison only)")
    args = parser.parse_args()

    cache = config.PROCESSED_DIR / "matches_normalized.csv"
    if args.download or not cache.exists():
        matches = odds_history.load_all()
        matches.to_csv(cache, index=False)
    else:
        matches = pd.read_csv(cache, parse_dates=["date"])

    speed_index = load_surface_speed_index(
        config.PROCESSED_DIR / "ta_surface_speed_history.csv", config.START_SEASON)
    bets, summary = run_backtest(
        matches, min_train_seasons=args.min_train_seasons,
        edge_threshold=args.edge_threshold, kelly_fraction=args.kelly_fraction,
        starting_bankroll=args.bankroll, surface_speed_index=speed_index,
        bet_price_col=args.bet_at, reference_col=args.priced_against,
        use_market=not args.no_market,
    )
    bets.to_csv(config.REPORTS_DIR / "backtest_bets.csv", index=False)
    (config.REPORTS_DIR / "backtest_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))

    if bets.empty:
        return

    print("\nBreakdown by segment (exploratory -- slice a dataset enough ways and")
    print("something always looks profitable; only pre-registered segments count):")
    for column in ("tour", "surface", "season"):
        if column not in bets.columns:
            continue
        seg = edge_audit.segment_report(bets, by=column)
        if seg.empty:
            continue
        print(f"\n  --- by {column} ---")
        print(seg[[column, "n_bets", "roi", "t_stat", "significant"]].to_string(index=False))
        seg.to_csv(config.REPORTS_DIR / f"backtest_by_{column}.csv", index=False)


if __name__ == "__main__":
    main()
