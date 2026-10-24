#!/usr/bin/env python3
"""Walk-forward evaluate the model on cached history and print metrics.

Run scripts/update_data.py first (or pass --download) to make sure
data/processed/matches_normalized.csv exists.
"""
import _bootstrap  # noqa: F401
import argparse

import pandas as pd

from tennissharp import config
from tennissharp.data import odds_history
from tennissharp.features import attach_market_probability, build_feature_table
from tennissharp.model import walk_forward_evaluate
from tennissharp.tourney_matching import load_surface_speed_index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="Re-download instead of using the cached CSV")
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--no-market", action="store_true",
                        help="Evaluate our features alone, without blending in the market price")
    args = parser.parse_args()

    cache = config.PROCESSED_DIR / "matches_normalized.csv"
    if args.download or not cache.exists():
        matches = odds_history.load_all()
        matches.to_csv(cache, index=False)
    else:
        matches = pd.read_csv(cache, parse_dates=["date"])

    speed_index = load_surface_speed_index(
        config.PROCESSED_DIR / "ta_surface_speed_history.csv", config.START_SEASON)
    table, _ = build_feature_table(matches, surface_speed_index=speed_index)
    if not args.no_market:
        table = attach_market_probability(table)

    metrics = walk_forward_evaluate(table, min_train_seasons=args.min_train_seasons,
                                     use_market=not args.no_market)
    metrics.to_csv(config.REPORTS_DIR / "model_metrics.csv", index=False)
    print(metrics.to_string(index=False))
    print(f"\nMean accuracy: {metrics['accuracy'].mean():.4f}  "
          f"Mean log loss: {metrics['log_loss'].mean():.4f}  "
          f"Mean Brier: {metrics['brier_score'].mean():.4f}")

    if "market_log_loss" in metrics.columns:
        ours, market = metrics["log_loss"].mean(), metrics["market_log_loss"].mean()
        print(f"Mean market log loss: {market:.4f}   (ours: {ours:.4f})")
        seasons_won = int(metrics["beats_market"].sum())
        print(f"\nSeasons where we beat the market: {seasons_won}/{len(metrics)}")
        if ours >= market:
            print("We do not beat the market. That is the expected result and it means\n"
                  "this model cannot be used to bet profitably -- run scripts/audit_edge.py\n"
                  "for the full diagnosis.")


if __name__ == "__main__":
    main()
