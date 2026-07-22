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
3. Ingests [Tennis Abstract](https://tennisabstract.com)'s own Elo ratings
   (the reference the wider tennis-analytics community treats as
   authoritative) and its per-tournament-edition surface-speed ratings, and
   pulls schedule/odds/head-to-head data from
   [TennisExplorer](https://www.tennisexplorer.com) — see "Data sources" below
   for exactly how each one is used and why.
4. Trains a calibrated gradient-boosting classifier to estimate P(player A wins),
   validated walk-forward (train on the past, test on the next season only —
   the only honest way to validate a time series like this).
5. De-vigs bookmaker odds (multiplicative and Shin's method) to get a "true"
   market probability, and flags bets where the model's probability clears
   the market's by a threshold (a value bet).
6. Backtests that strategy with fractional-Kelly staking and reports ROI.
7. Optionally checks *live* odds (via [The Odds API](https://the-odds-api.com),
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

## Data sources

| Source | What we take from it | Refreshed | Used for |
|---|---|---|---|
| [tennis-data.co.uk](http://www.tennis-data.co.uk/) | ATP/WTA results + odds (2000/2007+) | every `update_data.py` run | primary training data, backtesting |
| [Tennis Abstract](https://tennisabstract.com) Elo ratings | overall/hard/clay/grass Elo, current snapshot | every run (`data/processed/ta_elo_current.csv`) | **live/current-match scoring and cross-checks only** — see caveat below |
| Tennis Abstract surface speed | per-tournament-*edition* ace-rate-based speed rating | every run (`data/processed/ta_surface_speed_history.csv`) | a real training feature (`tourney_surface_speed`), safe for backtesting |
| [TennisExplorer](https://www.tennisexplorer.com) | today/tomorrow's schedule + odds, on-demand head-to-head | every run (`data/processed/tennisexplorer_upcoming.csv`) | free alternative to The Odds API for live schedule/odds; `fetch_head_to_head()` for on-demand H2H lookups |
| [The Odds API](https://the-odds-api.com) | live bookmaker odds | on demand (`find_value_bets.py`) | live value-bet scoring (needs your own key) |

**Why Tennis Abstract's Elo isn't a training feature but its surface speed is:**
Elo ratings there are a *live snapshot* — there's no way to ask "what was
this rating on 2019-03-04?", so joining today's rating onto a 2019 match
would leak the future into the past (the single most dangerous mistake in a
backtested trading/betting system). The surface-speed report, by contrast,
publishes one dated rating per *tournament edition*, so a 2019 tournament's
rating reflects only information available when that tournament was played —
safe to join into historical training data. `tourney_matching.py`'s docstring
spells this out; if you extend the pipeline, keep that distinction in mind.

**Why `tennisabstract.com/cgi-bin/leaders.cgi` (and the WTA/51-100/challenger
variants) aren't wired in:** those leaderboards are built client-side from a
large, undocumented internal JavaScript array — reproducing them correctly
would mean either executing that JS (a headless-browser dependency we
couldn't validate from this sandboxed dev session, though it should work fine
in GitHub Actions' unrestricted network) or reverse-engineering an ambiguous,
inconsistent-length array format blind. Both risk silently feeding wrong
numbers into a betting model, so this was deliberately left out rather than
shipped unverified — a reasonable next step if you want to pursue it.

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
# 1. Download all data sources, recompute Elo ratings, retrain the model
python scripts/update_data.py

# 2. Walk-forward accuracy/calibration report
python scripts/train_model.py

# 3. Historical value-betting backtest (ROI, hit rate, edge vs. Pinnacle)
python scripts/run_backtest.py --edge-threshold 0.03 --kelly-fraction 0.25

# 4. Live value bets (needs ODDS_API_KEY, and step 1 run at least once)
python scripts/find_value_bets.py
```

Outputs land in `data/processed/` (Elo ratings, normalized match history,
Tennis Abstract Elo + surface speed, TennisExplorer's upcoming schedule),
`data/reports/` (update summary, model metrics, backtest results), and
`models/` (the trained classifier + persisted player state for live scoring).

For on-demand head-to-head lookups (not part of the automated pipeline, since
it's one HTTP request per matchup):

```python
from tennissharp.data.tennisexplorer import fetch_matches, fetch_head_to_head, head_to_head_summary

today = fetch_matches(0)  # gives player1_slug/player2_slug to feed below
h2h = fetch_head_to_head("zverev-6f768", "sinner-8b8e8")
print(head_to_head_summary(h2h, "Zverev A.", "Sinner J."))
```

## Keeping data up to date automatically

`.github/workflows/update-data.yml` runs `update_data.py` and
`run_backtest.py` daily via cron and commits any changed files back to the
repo. GitHub only fires scheduled workflows from the files as they exist on
the **default branch**, so merge this workflow there for the schedule to take
effect; `workflow_dispatch` lets you trigger it manually from the Actions tab
in the meantime.

## Telegram bot & REST API

Two optional front ends sit on top of the same pipeline -- a Telegram bot for
chatting with it directly, and a REST API if you'd rather build your own app
(mobile, web, whatever). Both are thin wrappers around
`src/tennissharp/service.py`, so they always answer with exactly the same
data; neither reads a CSV directly.

**Telegram bot setup:**
1. Message [@BotFather](https://t.me/BotFather) on Telegram, `/newbot`, and
   copy the token it gives you into `config/.env` as `TELEGRAM_BOT_TOKEN`.
2. `python scripts/update_data.py` at least once, so there's data to answer with.
3. `python scripts/run_telegram_bot.py` — runs until you stop it (Ctrl+C or a
   process manager). It's long-polling, so it needs to keep running somewhere
   (a small VPS, your own machine, or the Docker image below) — GitHub Actions
   jobs time out and aren't a fit for this part.

Commands: `/rankings [atp|wta] [ta|own]`, `/surface [Turniername]`,
`/upcoming [atp|wta]`, `/h2h Spieler1 Spieler2`, `/valuebets`. Set
`TELEGRAM_CHAT_ID` (and optionally `TELEGRAM_DIGEST_HOUR_UTC`, default 7 UTC)
to also get a daily rankings push instead of only answering on demand.

**REST API:**
```bash
python scripts/run_api.py --port 8000
# then e.g.
curl "http://localhost:8000/rankings?tour=atp&source=ta&top_n=10"
curl "http://localhost:8000/upcoming?tour=wta"
curl "http://localhost:8000/h2h?player1=Djokovic&player2=Nadal"
curl "http://localhost:8000/value-bets"   # needs ODDS_API_KEY server-side
```
Interactive docs (Swagger UI) are auto-generated at `/docs` once it's
running. Every endpoint mirrors a `service.py` function 1:1 -- see that
module's docstrings for exactly what each one reads and any caveats (e.g.
`/rankings?source=own` doesn't separate ATP/WTA, since our own homegrown Elo
snapshot doesn't tag which tour a player belongs to; use `source=ta` for a
tour-filtered list). `/h2h` only resolves players currently listed in
TennisExplorer's today/tomorrow schedule cache, not an arbitrary historical
lookup.

**Running either in Docker:**
```bash
docker build -t tennissharpbot .
docker run --env-file config/.env tennissharpbot python scripts/run_telegram_bot.py
docker run --env-file config/.env -p 8000:8000 tennissharpbot python scripts/run_api.py --host 0.0.0.0
```
The image bakes in whatever's in `data/`/`models/` at build time; run
`scripts/update_data.py` on a schedule outside the container (or rebuild
periodically) to keep it current. Not built/tested against a live Docker
daemon in this repo's dev environment — standard `python:3.11-slim` pattern,
but verify it builds before relying on it.

Both front ends carry the same disclaimer as the CLI: this ranks candidates
by modelled edge vs. the de-vigged market, it is not financial advice, and
the honest backtest result below applies here too.

## Honest backtest result — please read this

Running `scripts/run_backtest.py` on the full default dataset (ATP + WTA,
2010 onward), with a 3% edge-vs-Pinnacle threshold and quarter-Kelly staking:

```
n_bets: 33108   win_rate: 38.5%   roi_on_turnover: -15.8%
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
  config.py             paths + env-based settings
  data/
    odds_history.py     tennis-data.co.uk download + normalization
    tennisabstract.py   Tennis Abstract Elo + surface-speed scraping
    tennisexplorer.py   TennisExplorer schedule/odds/H2H scraping
    live_odds.py        The Odds API client (live odds, optional)
  elo.py                overall + surface Elo engine
  features.py           leakage-free feature table + LiveState for live scoring
  tourney_matching.py    joins TA surface-speed ratings onto historical matches
  model.py               calibrated gradient-boosting classifier, walk-forward eval
  odds_math.py           implied probability, multiplicative + Shin devigging
  staking.py             fractional Kelly bet sizing
  backtest.py            historical value-betting simulation
  value_finder.py        live odds -> value bet candidates (+ TA Elo cross-check)
  name_matching.py       'Lastname F.' <-> full-name matching (live use only)
  service.py             shared data-access layer used by both front ends below
  api.py                 FastAPI REST API (build your own app on top)
  bot/
    telegram_bot.py      Telegram bot (commands + optional daily digest)
    formatting.py        pure text formatters (Telegram HTML), unit-testable
scripts/                 CLI entry points (see Usage above)
tests/                   unit tests (pytest) + tests/fixtures (cached sample HTML)
.github/workflows/       scheduled data/model refresh
Dockerfile               runs the bot or the API (see "Telegram bot & REST API")
```
