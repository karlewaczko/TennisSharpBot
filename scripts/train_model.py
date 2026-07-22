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
from tennissharp.features import build_feature_table
from tennissharp.model import walk_forward_evaluate
from tennissharp.tourney_matching import load_surface_speed_index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="Re-download instead of using the cached CSV")
    parser.add_argument("--min-train-seasons", type=int, default=3)
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
    metrics = walk_forward_evaluate(table, min_train_seasons=args.min_train_seasons)
    metrics.to_csv(config.REPORTS_DIR / "model_metrics.csv", index=False)
    print(metrics.to_string(index=False))
    print(f"\nMean accuracy: {metrics['accuracy'].mean():.4f}  "
          f"Mean log loss: {metrics['log_loss'].mean():.4f}  "
          f"Mean Brier: {metrics['brier_score'].mean():.4f}")


if __name__ == "__main__":
    main()
