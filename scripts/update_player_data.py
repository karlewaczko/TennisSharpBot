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

See tennissharp/player_data.py for sources and columns.

Tennis Abstract refuses GitHub's runners (HTTP 403, measured 2026-10-24),
so its pages are read by a weekly Claude Code scheduled task that runs this
script from an environment the site accepts and pushes the result; the
GitHub job then rebuilds the table around the stored ratings. A refused
fetch is therefore a warning, not a failure. The exit code is 1 only when
the statistics could not be built, or when the stored Tennis Abstract copy
is older than TA_MAX_AGE_DAYS -- that is, when the weekly refresh has
actually stopped working.

    --surface-speed   also refresh Tennis Abstract's surface-speed history
"""
import _bootstrap  # noqa: F401
import argparse
import json
import logging
import sys

from tennissharp import player_data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surface-speed", action="store_true",
                    help="also refresh Tennis Abstract's surface-speed history")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    meta = player_data.refresh(surface_speed=args.surface_speed)
    age = player_data.ta_age_days(meta)
    print(json.dumps({**{k: meta[k] for k in ("ta_elo_last_update", "ta_yelo_last_update",
                                               "ta_fetched_at", "stats_window", "stats_last_match",
                                               "players")},
                      "ta_age_days": None if age is None else round(age, 2)}, indent=1))
    for err in meta["errors"]:
        # A GitHub Actions annotation: shown on the run's summary page.
        print(f"::warning::{err}")
    if not meta.get("statistics_ok"):
        print("::error::Spielerstatistiken konnten nicht berechnet werden.")
        return 1
    if age is None or age > player_data.TA_MAX_AGE_DAYS:
        print(f"::error::Tennis-Abstract-Daten sind aelter als {player_data.TA_MAX_AGE_DAYS} Tage "
              f"-- der woechentliche Abruf erreicht die Seite nicht mehr.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
