#!/usr/bin/env python3
"""Refresh Tennis Abstract's Elo and yElo and the complete player table.

    python scripts/update_player_data.py

Runs every Tuesday from .github/workflows/update-data.yml; Tennis Abstract
updates its leaderboards weekly, usually on Monday. Writes, under
data/processed/:

    player_profiles_atp.csv, player_profiles_wta.csv   every player: Elo,
        surface Elo, yElo, and last-52-week serve, return, hold and break
        statistics overall and on hard, clay and grass
    player_profiles_meta.json      update dates, counts, errors
    ta_elo_*.csv, ta_yelo_current.csv, ta_elo_history.csv, ta_leaders_*.csv

See tennissharp/player_data.py for sources and columns. Exits 1 when a
source failed -- after writing everything it could -- so a scheduled run
shows red instead of quietly publishing last week's numbers.
"""
import _bootstrap  # noqa: F401
import json
import logging
import sys

from tennissharp import player_data


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    meta = player_data.refresh()
    print(json.dumps({k: meta[k] for k in ("ta_elo_last_update", "ta_yelo_last_update",
                                            "stats_window", "stats_last_match", "players")},
                     indent=1))
    for err in meta["errors"]:
        # A GitHub Actions annotation: shown on the run's summary page.
        print(f"::warning::{err}")
    return 1 if meta["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
