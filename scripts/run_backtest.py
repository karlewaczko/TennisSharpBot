#!/usr/bin/env python3
"""Simulate the value-betting strategy over historical data and report ROI.

Reminder: a positive backtest ROI on historical odds is a *necessary*, not
sufficient, condition for real profitability -- it doesn't account for bet
limits/limiting by bookmakers, odds moving between your decision and your
bet being placed, or the fact this model has never seen live markets.
"""
import _bootstrap  # noqa: F401
import argparse
import json

import pandas as pd

from tennissharp import config
from tennissharp.backtest import run_backtest
from tennissharp.data import odds_history


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--edge-threshold", type=float, default=0.03)
    parser.add_argument("--kelly-fraction", type=float, default=0.25)
    parser.add_argument("--bankroll", type=float, default=10_000.0)
    parser.add_argument("--min-train-seasons", type=int, default=5)
    args = parser.parse_args()

    cache = config.PROCESSED_DIR / "matches_normalized.csv"
    if args.download or not cache.exists():
        matches = odds_history.load_all()
        matches.to_csv(cache, index=False)
    else:
        matches = pd.read_csv(cache, parse_dates=["date"])

    bets, summary = run_backtest(
        matches, min_train_seasons=args.min_train_seasons,
        edge_threshold=args.edge_threshold, kelly_fraction=args.kelly_fraction,
        starting_bankroll=args.bankroll,
    )
    bets.to_csv(config.REPORTS_DIR / "backtest_bets.csv", index=False)
    (config.REPORTS_DIR / "backtest_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
