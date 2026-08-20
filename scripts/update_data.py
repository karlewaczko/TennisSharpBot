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
import pandas as pd

from tennissharp import config, model as model_mod
from tennissharp.data import odds_history, tennisabstract, tennisexplorer
from tennissharp.features import attach_market_probability, build_feature_table
from tennissharp.tourney_matching import build_surface_speed_index

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _fetch_tennisabstract_data() -> tuple[pd.DataFrame, dict]:
    """Tennis Abstract Elo + surface-speed ratings. Best-effort: a hiccup
    fetching this supplementary source shouldn't abort the whole update.
    """
    try:
        ta_elo = tennisabstract.fetch_all_elo_ratings()
        ta_elo.to_csv(config.PROCESSED_DIR / "ta_elo_current.csv", index=False)
        logger.info("Fetched %d Tennis Abstract Elo ratings", len(ta_elo))

        # Standalone per-tour files, same full schema (overall + hElo/cElo/gElo).
        for tour in ("atp", "wta"):
            tour_elo = tennisabstract.filter_by_tour(ta_elo, tour=tour)
            tour_elo.to_csv(config.PROCESSED_DIR / f"ta_elo_{tour}_general.csv", index=False)
            logger.info("Saved %d %s Elo ratings (overall + hElo/cElo/gElo)",
                        len(tour_elo), tour.upper())
    except Exception:
        logger.exception("Failed to fetch Tennis Abstract Elo ratings -- continuing without them")
        ta_elo = pd.DataFrame()

    try:
        speed_history = tennisabstract.fetch_surface_speed_history(config.START_SEASON)
        speed_history.to_csv(config.PROCESSED_DIR / "ta_surface_speed_history.csv", index=False)
        logger.info("Fetched %d Tennis Abstract surface-speed ratings", len(speed_history))
        speed_index = build_surface_speed_index(speed_history)
    except Exception:
        logger.exception("Failed to fetch Tennis Abstract surface-speed ratings -- continuing without them")
        speed_index = {}

    return ta_elo, speed_index


def _fetch_tennisexplorer_schedule() -> pd.DataFrame:
    """Today + tomorrow's scheduled matches and odds from TennisExplorer --
    a free complement/alternative to The Odds API for the live value finder.
    Best-effort like the Tennis Abstract fetches above.
    """
    try:
        upcoming = pd.concat(
            [tennisexplorer.fetch_matches(0), tennisexplorer.fetch_matches(1)],
            ignore_index=True,
        )
        upcoming.to_csv(config.PROCESSED_DIR / "tennisexplorer_upcoming.csv", index=False)
        logger.info("Fetched %d upcoming TennisExplorer matches", len(upcoming))
        return upcoming
    except Exception:
        logger.exception("Failed to fetch TennisExplorer schedule -- continuing without it")
        return pd.DataFrame()


def main() -> None:
    logger.info("Downloading match+odds history for tours: %s", config.TOURS)
    matches = odds_history.load_all()
    if matches.empty:
        logger.error("No data downloaded -- aborting update.")
        return
    matches.to_csv(config.PROCESSED_DIR / "matches_normalized.csv", index=False)
    logger.info("Loaded %d matches (%s to %s)", len(matches),
                matches["date"].min().date(), matches["date"].max().date())

    ta_elo, speed_index = _fetch_tennisabstract_data()
    _fetch_tennisexplorer_schedule()

    table, state = build_feature_table(matches, surface_speed_index=speed_index)
    joblib.dump(state, config.MODELS_DIR / "live_state.joblib")

    snapshot = state.elo.snapshot()
    snapshot.to_csv(config.PROCESSED_DIR / "elo_ratings_current.csv", index=False)

    # Blend the de-vigged market price into the model. Measured on 55k matches,
    # this cuts out-of-sample log loss from 0.618 to 0.595 -- by far the single
    # biggest accuracy gain available. It does NOT create a betting edge (see
    # the README); it makes the forecasts themselves much better.
    table = attach_market_probability(table)
    n_with_odds = int(table["market_prob_p1"].notna().sum())
    logger.info("Training model on full history for live use (%d/%d matches have a "
                "market price to blend in)...", n_with_odds, len(table))
    full_model = model_mod.train(table, use_market=n_with_odds > 0)
    model_mod.save(full_model, config.MODELS_DIR / "win_probability_model.joblib")

    _write_report(matches, snapshot, ta_elo)
    logger.info("Update complete.")


def _write_report(matches, snapshot, ta_elo) -> None:
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
    if ta_elo is not None and not ta_elo.empty:
        lines += [
            "",
            "## Tennis Abstract Elo ratings (top 10 per tour, reference/authoritative)",
            "",
        ]
        for tour in sorted(ta_elo["tour"].unique()):
            lines += [
                f"### {tour.upper()}",
                "",
                ta_elo[ta_elo["tour"] == tour].sort_values("elo_rank").head(10)[
                    ["elo_rank", "player", "elo", "helo", "celo", "gelo"]
                ].to_markdown(index=False),
                "",
            ]
    (config.REPORTS_DIR / "latest_update.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
