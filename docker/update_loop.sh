#!/bin/sh
# Runs scripts/update_data.py once immediately, then every 24h forever.
# This is what keeps the bot/API's data current without needing a separate
# cron daemon inside the container.
set -u

INTERVAL_SECONDS="${UPDATE_INTERVAL_SECONDS:-86400}"

while true; do
    echo "[updater] $(date -u +%Y-%m-%dT%H:%M:%SZ) starting update_data.py"
    if python scripts/update_data.py; then
        echo "[updater] update finished OK"
    else
        echo "[updater] update FAILED -- keeping previously loaded data, will retry next cycle"
    fi
    echo "[updater] sleeping ${INTERVAL_SECONDS}s"
    sleep "$INTERVAL_SECONDS"
done
