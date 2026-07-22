# TennisSharpBot

Surface-Elo + machine-learning tennis match modeling, historical backtesting
against real bookmaker odds, and (optional) live value-bet detection.

**Read the disclaimer at the bottom before using this for anything real.**

## What this is

A pipeline that:

1. Downloads ATP + WTA match results *and* bookmaker odds (incl. Pinnacle) from
   [tennis-data.co.uk](http://www.tennis-data.co.uk/) — one combined source, so
   no fuzzy player-name matching is needed between a results feed and an odds feed.
2. Builds overall + surface-specific Elo ratings chronologically (no
   lookahead), plus recent-form and head-to-head features.
3. Trains a calibrated gradient-boosting classifier to estimate P(player A wins),
   validated walk-forward (train on the past, test on the next season only —
   the only honest way to validate a time series like this).
4. De-vigs bookmaker odds (multiplicative and Shin's method) to get a "true"
   market probability, and flags bets where the model's probability clears
   the market's by a threshold (a value bet).
5. Backtests that strategy with fractional-Kelly staking and reports ROI.
6. Optionally checks *live* odds (via [The Odds API](https://the-odds-api.com),
   your own API key) against the model for today's matches.

## Why tennis-data.co.uk instead of the Sackmann `tennis_atp`/`tennis_wta` repos

Those repos (the usual starting point for tennis modeling) are not reachable
on GitHub as of 2026-07 (both the repo pages and raw file downloads 404 from
multiple independent network paths). tennis-data.co.uk covers ATP since 2000
and WTA since 2007 with results and odds combined in one file per season, and
is still live and updating. If you have access to a Sackmann-schema dataset
(e.g. `Tennismylife/TML-Database`, a community-maintained continuation) you
can extend `src/tennissharp/data/` to merge it in for deeper history — see
`name_matching.py`, which exists for exactly this "full name vs `Lastname F.`"
matching problem when combining sources that don't share a schema.

## Setup

```bash
pip install -r requirements.txt
pip install -e .   # so `import tennissharp` works from anywhere
cp config/settings.example.env config/.env  # then edit config/.env
```

`config/.env` is optional — everything except live value-bet finding works
with zero configuration. Key settings:

- `TOURS` — `atp`, `wta`, or `atp,wta` (default: both)
- `START_SEASON` — first season to pull (default 2010; earliest possible is
  2000 for ATP / 2007 for WTA)
- `ODDS_API_KEY` — only needed for `scripts/find_value_bets.py`

## Usage

```bash
# 1. Download data, recompute Elo ratings, retrain the model
python scripts/update_data.py

# 2. Walk-forward accuracy/calibration report
python scripts/train_model.py

# 3. Historical value-betting backtest (ROI, hit rate, edge vs. Pinnacle)
python scripts/run_backtest.py --edge-threshold 0.03 --kelly-fraction 0.25

# 4. Live value bets (needs ODDS_API_KEY, and step 1 run at least once)
python scripts/find_value_bets.py
```

Outputs land in `data/processed/` (Elo ratings, normalized match history),
`data/reports/` (update summary, model metrics, backtest results), and
`models/` (the trained classifier + persisted player state for live scoring).

## Keeping data up to date automatically

`.github/workflows/update-data.yml` runs `update_data.py` and
`run_backtest.py` daily via cron and commits any changed files back to the
repo. GitHub only fires scheduled workflows from the files as they exist on
the **default branch**, so merge this workflow there for the schedule to take
effect; `workflow_dispatch` lets you trigger it manually from the Actions tab
in the meantime.

## Honest backtest result — please read this

Running `scripts/run_backtest.py` on the full default dataset (ATP + WTA,
2010 onward), with a 3% edge-vs-Pinnacle threshold and quarter-Kelly staking:

```
n_bets: 33083   win_rate: 38.6%   roi_on_turnover: -16.3%
```

The underlying model is reasonably calibrated in aggregate (~65% accuracy,
Brier ≈ 0.22 out of sample — in line with published tennis models), verified
with a reliability curve. But picking only the matches where this model
disagrees most with Pinnacle selects for the model's own biggest mistakes
more often than genuine market inefficiencies, because a 6-feature Elo/form/
H2H model is simply working with less information than one of the world's
sharpest sportsbooks. This matches exactly what the professional-betting
literature says: **a real, sustainable edge against Pinnacle requires
information the market doesn't already have** (point-by-point stats, injury/
fatigue intel, surface-transition effects, etc.) — not just re-deriving Elo
from public results. Treat every number this tool produces as a research
signal to investigate further, never as a ready-made bet.

## Legal & responsible gambling (Germany)

Professional sports betting is high-variance and the overwhelming majority of
people who try it lose money long-term, even with reasonable models. This
project is for research/education. If you do bet:

- Only use operators licensed by the **GGL** (Gemeinsame Glücksspielbehörde
  der Länder); check the current whitelist.
- **LUGAS** enforces a cross-operator deposit limit of **€1,000/month** per
  player in Germany — it is not optional and applies across all licensed
  operators simultaneously.
- **OASIS** is the national self-exclusion system; use it if betting stops
  being fun or affordable.
- Pinnacle is not GGL-licensed for the German market; accessing it via a
  betting broker sits in a legal grey area (reduced consumer protection, and
  tax/account risk) — understand that before going down that route.
- Never stake money you can't afford to lose, and never chase losses.

## Repository layout

```
src/tennissharp/
  config.py          paths + env-based settings
  data/
    odds_history.py  tennis-data.co.uk download + normalization
    live_odds.py      The Odds API client (live odds, optional)
  elo.py              overall + surface Elo engine
  features.py          leakage-free feature table + LiveState for live scoring
  model.py             calibrated gradient-boosting classifier, walk-forward eval
  odds_math.py          implied probability, multiplicative + Shin devigging
  staking.py             fractional Kelly bet sizing
  backtest.py            historical value-betting simulation
  value_finder.py         live odds -> value bet candidates
  name_matching.py         'Lastname F.' <-> full-name matching (live use only)
scripts/                  CLI entry points (see Usage above)
tests/                    unit tests (pytest)
.github/workflows/        scheduled data/model refresh
```
