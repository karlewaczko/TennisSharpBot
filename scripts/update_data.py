#!/usr/bin/env python3
"""Refresh match/odds history, recompute Elo + model artifacts.

Run this regularly (a daily GitHub Actions cron does it automatically --
see .github/workflows/update-data.yml) to keep ratings and the live model
current. Safe to re-run any time; each run re-downloads the current season
and reuses cached files for closed seasons.
"""
import _bootstrap  # noqa: F401
import datetime as dt
import logging

import joblib

from tennissharp import config, model as model_mod
from tennissharp.data import odds_history
from tennissharp.features import build_feature_table

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Downloading match+odds history for tours: %s", config.TOURS)
    matches = odds_history.load_all()
    if matches.empty:
        logger.error("No data downloaded -- aborting update.")
        return
    matches.to_csv(config.PROCESSED_DIR / "matches_normalized.csv", index=False)
    logger.info("Loaded %d matches (%s to %s)", len(matches),
                matches["date"].min().date(), matches["date"].max().date())

    table, state = build_feature_table(matches)
    joblib.dump(state, config.MODELS_DIR / "live_state.joblib")

    snapshot = state.elo.snapshot()
    snapshot.to_csv(config.PROCESSED_DIR / "elo_ratings_current.csv", index=False)

    logger.info("Training model on full history for live use...")
    full_model = model_mod.train(table)
    model_mod.save(full_model, config.MODELS_DIR / "win_probability_model.joblib")

    _write_report(matches, snapshot)
    logger.info("Update complete.")


def _write_report(matches, snapshot) -> None:
    lines = [
        f"# TennisSharpBot data update ({dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')})",
        "",
        f"- Matches in history: {len(matches)}",
        f"- Date range: {matches['date'].min().date()} to {matches['date'].max().date()}",
        f"- Tours: {', '.join(config.TOURS)}",
        "",
        "## Top 10 current overall Elo (players with 50+ matches on record)",
        "",
        snapshot[snapshot["matches_played"] >= 50].head(10)[
            ["player", "elo_overall", "matches_played"]
        ].to_markdown(index=False),
    ]
    (config.REPORTS_DIR / "latest_update.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
