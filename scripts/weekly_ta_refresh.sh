#!/usr/bin/env bash
# The weekly Tennis Abstract refresh, as one command:
#
#     bash scripts/weekly_ta_refresh.sh
#
# Run every Tuesday from the project's Claude Code chat by a scheduled task
# (Tennis Abstract answers GitHub's runners with HTTP 403, so this part
# cannot run in GitHub Actions). It works on a separate checkout of
# origin/main, so whatever branch the calling checkout is on stays as it
# is, refreshes Tennis Abstract's Elo, yElo and surface speed plus the
# player table, commits only data/processed and pushes that to main.
#
# COMMIT_TRAILER, if set, is appended to the commit message (attribution
# lines). Exit code: that of scripts/update_player_data.py, or 1 when the
# push failed.
set -uo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
cleanup() { git -C "$repo" worktree remove --force "$work" >/dev/null 2>&1 || rm -rf "$work"; }
trap cleanup EXIT

git -C "$repo" fetch -q origin main || { echo "FEHLER: git fetch origin main"; exit 1; }
git -C "$repo" worktree add -q --detach "$work" origin/main || { echo "FEHLER: worktree"; exit 1; }
cd "$work"

python -m pip install -q -r requirements.txt >/dev/null 2>&1 || python -m pip install -q -r requirements.txt
python scripts/update_player_data.py --surface-speed > "$work/refresh.log" 2>&1
status=$?
grep -E "^INFO|::warning|::error" "$work/refresh.log" | sed 's/^/  /'

git add data/processed
pushed="nein (keine Aenderungen)"
if ! git diff --cached --quiet; then
  msg="Weekly Tennis Abstract refresh ($(date -u +%Y-%m-%d))"
  if [ -n "${COMMIT_TRAILER:-}" ]; then
    msg="$(printf '%s\n\n%s' "$msg" "$COMMIT_TRAILER")"
  fi
  git commit -q -m "$msg"
  pushed="FEHLGESCHLAGEN"
  for attempt in 1 2 3; do
    # Logs merge by union (.gitattributes); for regenerated files this
    # run's build wins.
    if git fetch -q origin main && git rebase -q -X theirs origin/main && git push -q origin HEAD:main; then
      pushed="ja ($(git rev-parse --short HEAD))"
      break
    fi
    git rebase --abort >/dev/null 2>&1 || true
    sleep 10
  done
fi

python - <<'PY'
import json
m = json.load(open("data/processed/player_profiles_meta.json"))
p = m["players"]
print(f"Tennis-Abstract-Stand: {m['ta_elo_last_update']}, gelesen {m.get('ta_fetched_at', {}).get('elo')}")
print(f"Spieler: ATP {p['atp']['total']} (Elo {p['atp']['with_elo']}, Statistik {p['atp']['with_stats']}), "
      f"WTA {p['wta']['total']} (Elo {p['wta']['with_elo']}, Statistik {p['wta']['with_stats']})")
print("Fehler: " + ("; ".join(m["errors"]) if m["errors"] else "keine"))
PY
echo "Gepusht: $pushed"
case "$pushed" in FEHLGESCHLAGEN) exit 1;; esac
exit "$status"
