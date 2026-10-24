#!/usr/bin/env python3
"""Refresh match/odds history, recompute Elo + model artifacts.

Run this regularly (a daily GitHub Actions cron does it automatically --
see .github/workflows/update-data.yml) to keep ratings and the live model
current. Safe to re-run any time; each run re-downloads the current season
and reuses cached files for closed seasons.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import logging

import joblib
import pandas as pd

from tennissharp import config, model as model_mod, player_data
from tennissharp.data import odds_history, tennisabstract, tennisexplorer, tennismylife
from tennissharp.features import attach_market_probability, build_feature_table
from tennissharp.tourney_matching import build_surface_speed_index

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _fetch_surface_speed() -> dict:
    """Tennis Abstract's surface-speed ratings per tournament edition, a
    trained feature. Best-effort: a hiccup here must not abort the update.
    (The Elo and yElo leaderboards and the player statistics are refreshed
    by player_data.refresh, which the weekly job also runs on its own.)
    """
    path = config.PROCESSED_DIR / "ta_surface_speed_history.csv"
    try:
        speed_history = tennisabstract.fetch_surface_speed_history(config.START_SEASON)
        if speed_history.empty:
            raise RuntimeError("no surface-speed ratings returned")
        speed_history.to_csv(path, index=False)
        logger.info("Fetched %d Tennis Abstract surface-speed ratings", len(speed_history))
        return build_surface_speed_index(speed_history)
    except Exception as exc:
        # `tourney_surface_speed` is a trained feature: retraining with an
        # empty index would set it to the neutral default on every row and
        # teach the model that speed does not exist. The committed history
        # (refreshed weekly by scripts/update_player_data.py) stands in.
        logger.warning("Surface-speed ratings not refreshed (%s) -- using the saved history", exc)
        if path.exists():
            saved = pd.read_csv(path, parse_dates=["date"])
            return build_surface_speed_index(saved)
        return {}


def _refresh_player_data() -> None:
    """Tennis Abstract Elo + yElo, the dated Elo history, the complete player
    table and the leader tables -- see tennissharp/player_data.py."""
    try:
        meta = player_data.refresh()
        for err in meta["errors"]:
            logger.warning(err)
        logger.info("Player table: %s", meta["players"])
    except Exception:
        logger.exception("Player data refresh failed -- continuing")


SCHEDULE_DAYS = (0, 1, 2)


def _fetch_tennisexplorer_schedule() -> pd.DataFrame:
    """The next few days of scheduled matches and odds from TennisExplorer --
    a free complement/alternative to The Odds API for the live value finder.
    Best-effort like the Tennis Abstract fetches above.

    Three days rather than two: today's card is mostly played out by the
    afternoon, and the day after tomorrow is where the earliest prices sit
    (a sample taken on a Saturday: 41 open matches with odds today, 91
    tomorrow, 26 the day after).
    """
    try:
        upcoming = pd.concat(
            [tennisexplorer.fetch_matches(d) for d in SCHEDULE_DAYS],
            ignore_index=True,
        )
        # The pages overlap around midnight in the site's timezone, and a
        # match listed twice would be scored twice on the dashboard.
        upcoming = upcoming.drop_duplicates(subset="match_id", keep="first")
        upcoming.to_csv(config.PROCESSED_DIR / "tennisexplorer_upcoming.csv", index=False)
        logger.info("Fetched %d upcoming TennisExplorer matches", len(upcoming))
        return upcoming
    except Exception:
        logger.exception("Failed to fetch TennisExplorer schedule -- continuing without it")
        return pd.DataFrame()


def _refresh_recent_play_index() -> None:
    """When each player last played, from a source that covers challengers
    and qualifying. Our own history does not, which is why the dashboard
    marked players stale who were in fact competing every week.
    """
    try:
        seen = tennismylife.last_seen_index(start_season=dt.date.today().year - 2)
        pd.to_pickle(seen, config.PROCESSED_DIR / "tml_last_seen.pkl")
        logger.info("Recent-play index: %d players", len(seen))
    except Exception:
        logger.exception("Failed to refresh the recent-play index -- continuing without it")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-player-data", action="store_true",
                    help="do not refresh Tennis Abstract Elo/yElo and the player table "
                         "(the weekly workflow runs scripts/update_player_data.py first)")
    args = ap.parse_args()

    # The sources that do not depend on tennis-data.co.uk come first: when
    # its Cloudflare front refuses the download (HTTP 403 seen 2026-10-22),
    # the recent-play index, the Tennis Abstract tables and the schedule
    # still refresh, and only the retrain is skipped. Before this ordering a
    # failed download left every one of them stale for the day as well.
    _refresh_recent_play_index()
    if not args.skip_player_data:
        _refresh_player_data()
    speed_index = _fetch_surface_speed()
    _fetch_tennisexplorer_schedule()

    logger.info("Downloading match+odds history for tours: %s", config.TOURS)
    matches = odds_history.load_all()
    if matches.empty:
        logger.error("No match history downloaded -- keeping the committed Elo state "
                     "and model; only the supplementary sources were refreshed.")
        # Surfaces on the GitHub Actions run page without failing the run:
        # the supplementary refreshes above did succeed.
        print("::warning::tennis-data.co.uk lieferte keine Historie -- Modell und Elo-Zustand "
              "bleiben auf dem letzten Stand.")
        return
    matches.to_csv(config.PROCESSED_DIR / "matches_normalized.csv", index=False)
    logger.info("Loaded %d matches (%s to %s)", len(matches),
                matches["date"].min().date(), matches["date"].max().date())

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

    ta_path = config.PROCESSED_DIR / "ta_elo_current.csv"
    ta_elo = pd.read_csv(ta_path) if ta_path.exists() else pd.DataFrame()
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
