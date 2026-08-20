# TennisSharpBot

Surface-Elo + machine-learning tennis match modeling, historical backtesting
against real bookmaker odds, and (optional) live value-bet detection.

**New here / no coding background?** Follow **[ANLEITUNG.md](ANLEITUNG.md)**
instead (German, step-by-step, no Python/git knowledge needed) — it walks
through installing Docker and running the Telegram bot with one script.
This README is the technical reference for everything under the hood.

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
   blended with the de-vigged market price, validated walk-forward (train on
   the past, test on the next season only — the only honest way to validate a
   time series like this). **68.3% accuracy, 0.587 log loss** out of sample
   across 14 seasons.
5. De-vigs bookmaker odds (multiplicative and Shin's method) to get a "true"
   market probability, and flags bets where the model's probability clears
   the market's by a threshold (a value bet).
6. Backtests that strategy with fractional-Kelly staking, reporting ROI **with
   t-statistics** and a segment breakdown.
7. **Audits itself** (`scripts/audit_edge.py`): checks whether the odds columns
   are really purchasable, whether the market is beatable at all, and whether
   the model adds anything the market doesn't already know. Read
   "Can this actually beat the bookmakers?" below before anything else.
8. Optionally checks *live* odds (via [The Odds API](https://the-odds-api.com),
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
| [Tennis Abstract](https://tennisabstract.com) Elo ratings | overall/hard/clay/grass Elo, current snapshot | every run (`data/processed/ta_elo_current.csv`); standalone per-tour files (same columns) in `ta_elo_atp_general.csv` / `ta_elo_wta_general.csv` | **live/current-match scoring and cross-checks only** — see caveat below |
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

# 3. Historical value-betting backtest (ROI + t-stats + segment breakdown)
python scripts/run_backtest.py --edge-threshold 0.03 --kelly-fraction 0.25

# 4. THE IMPORTANT ONE: is an edge even possible with this data?
#    Run this before believing any backtest, including the one above.
python scripts/audit_edge.py

# 5. Live value bets (needs ODDS_API_KEY, and step 1 run at least once)
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

**Fastest path:** run `./quickstart.sh` (macOS/Linux) or `./quickstart.ps1`
(Windows) — an interactive script that only needs Docker installed, asks a
few questions, and starts everything for you. See [ANLEITUNG.md](ANLEITUNG.md)
for a fully beginner-oriented walkthrough. The manual steps below are for
running things outside Docker or understanding what the script does.

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

**Automatic value-bet scanning:** set `TELEGRAM_VALUEBETS_INTERVAL_MINUTES`
(minutes between scans, e.g. `240` for every 4 hours; `0` = off, the default)
to have the bot itself call `service.get_value_bets()` on a
`job_queue.run_repeating` schedule and push a message to `TELEGRAM_CHAT_ID`
whenever it finds a *new* candidate above `TELEGRAM_VALUEBETS_EDGE_THRESHOLD`
(default 0.03) — needs both `TELEGRAM_CHAT_ID` and `ODDS_API_KEY` set.
Dedup logic lives in `bot/notifications.py` (pure, unit-tested, no Telegram
imports): each `(player, opponent, bookmaker, commence_time)` combination is
only alerted once, tracked in `context.bot_data` for the life of the process
(resets on restart — no database). Mind The Odds API's free-tier budget
(~500 requests/month, one request per active event per scan) when picking an
interval.

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

**Running in Docker (recommended, this is what quickstart.sh/.ps1 do):**
```bash
cp config/settings.example.env config/.env   # then fill in TELEGRAM_BOT_TOKEN etc.
docker compose up -d --build            # bot + api + auto-updater
docker compose up -d --build updater bot   # skip the API if you don't need it
```
`docker-compose.yml` runs three services off one image, sharing a data
volume: `updater` (runs `scripts/update_data.py` once immediately, then every
24h forever -- no separate cron needed), `bot`, and `api`. `bot`/`api` wait
for `updater`'s first pass to finish before starting (the image also ships
with the repo's already-committed data baked in, so that wait is usually
short). `docker compose logs -f` to watch it, `docker compose down` to stop
everything.

Standalone, without compose:
```bash
docker build -t tennissharpbot .
docker run --env-file config/.env tennissharpbot python scripts/run_telegram_bot.py
docker run --env-file config/.env -p 8000:8000 tennissharpbot python scripts/run_api.py --host 0.0.0.0
```

Verified in this dev environment: `docker compose config` renders the compose
file correctly and both `quickstart.sh`/`quickstart.ps1` were run end-to-end
against a stubbed `docker` command (covering the questions, `config/.env`
generation, and service selection logic). The actual `docker build`/`up`
could **not** be exercised here (no Docker daemon available in this sandbox) —
if something doesn't come up cleanly on your machine, `docker compose logs`
is the first place to look.

Both front ends carry the same disclaimer as the CLI: this ranks candidates
by modelled edge vs. the de-vigged market, it is not financial advice, and
the honest backtest result below applies here too.

## Can this actually beat the bookmakers? — measured, not guessed

**No. Not with this data.** That is a measurement, not an opinion, and
`scripts/audit_edge.py` reproduces every number below in about three minutes.

### The decisive test

The sharp question isn't "is our model accurate?" — it's **"given the
bookmaker's price, do our features add anything?"** If a model trained on
[market price + our features] can't beat one trained on [market price] alone,
out of sample, then we hold no information the market lacks, and no amount of
tuning will change that.

Walk-forward over 13 seasons and 55,124 matches:

| model | out-of-sample log loss |
|---|---|
| Pinnacle's de-vigged price alone | **0.59406** |
| our features alone (Elo, form, H2H, fatigue, surface speed) | 0.61842 |
| Pinnacle's price **+** our features | 0.59494 |

Adding everything we know to Pinnacle's price makes the forecast **worse**
(−0.00088). In 11 of 13 seasons there is no gain at all. For scale, a
genuinely useful feature set moves log loss by 0.005–0.02.

### Why: the market is extremely efficient

Pinnacle's de-vigged probabilities vs. realised win rates, 157k player-sides:

| implied | actual | error |
|---|---|---|
| 0.063 | 0.056 | −0.008 |
| 0.252 | 0.252 | −0.000 |
| 0.446 | 0.452 | +0.006 |
| 0.649 | 0.642 | −0.007 |
| 0.846 | 0.842 | −0.004 |
| 0.937 | 0.945 | +0.008 |

Largest error anywhere in the range: **0.0076**. There is no systematic
mispricing to exploit.

### A "+69% ROI" strategy that is worth exactly nothing

While building this, an apparent edge showed up: betting the *best available*
odds whenever they beat Pinnacle's fair price returned **+2.9% to +8.5% ROI**
with t-statistics above 5, stable across 15 years. It was completely fake, for
two independent reasons — both now caught automatically:

1. **The price wasn't real.** tennis-data.co.uk's "max" column implies
   *negative overround* — i.e. risk-free arbitrage — on **43% of matches**.
   Genuine simultaneous cross-book arbitrage in tennis occurs on a low
   single-digit percentage. That column is a running maximum over the
   market's lifetime: the best price any book offered at any moment. You
   cannot bet a price that existed for ten minutes three days ago.
   `run_backtest()` now **refuses** to price bets from it, and
   `edge_audit.price_attainability_report()` flags it automatically.
2. **The honest version is noise.** Repeat with bet365 — one real,
   simultaneously-quotable book — and the edge evaporates: +1.93% ROI at
   t=1.27. Year by year it reads +6.3%, −4.1%, −2.6%, −21.1%, +13.6% … The
   audit also surfaces a **+69.32% ROI over 265 bets at t=1.13** — which is
   simply what noise looks like when you slice hard enough. Any ROI reported
   here now carries a t-statistic, because **an ROI without a standard error
   is a rumour.**

### What did improve

Feeding the market price into the model (`use_market=True`, now the default)
cut out-of-sample log loss from 0.618 to 0.595 — a large, real gain — and cut
the backtest's loss from −15.8% to **−4.7% ROI**. That −4.7% is not a
disappointment; it is almost exactly the bookmaker's margin on the book being
bet into, which is the theoretically correct result for a model with no
informational edge. The old model lost 15.8% because it bet on its own
biggest *errors*; this one loses only the vig.

### Where a real edge could come from

Nothing below is a promise, and each is hard:

- **Beating the closing line**, by betting early before the market sharpens.
  Requires timestamped opening/closing odds; this dataset has one snapshot per
  match, so CLV genuinely cannot be measured here.
- **Lower tiers** (ITF, Challenger) where limits are small and lines are
  softer. This dataset is tour-level only.
- **In-play**, where prices move on every point and models can react faster
  than traders.
- **Secondary markets** (total games, set betting, handicaps), which get less
  sharp attention than match-winner.
- **Information the market lacks**: verified injury/illness news, on-site
  scouting, conditions. This is the only category that has ever reliably
  worked, and it isn't a modelling problem.

Even with a genuine edge, soft books limit or close winning accounts within
weeks — the practical constraint that ends most of these projects.

**Use this as a forecasting and research tool.** It is a good one. It is not
a way to make money betting, and the audit script exists so you never have to
take that on faith.

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
  model.py               calibrated GBM, optionally blended with the market price
  edge_audit.py          the honesty checks: attainability, calibration,
                         incremental information, ROI significance
  odds_math.py           implied probability, multiplicative + Shin devigging
  staking.py             fractional Kelly bet sizing
  backtest.py            historical value-betting simulation
  value_finder.py        live odds -> value bet candidates (+ TA Elo cross-check)
  name_matching.py       'Lastname F.' <-> full-name matching (live use only)
  service.py             shared data-access layer used by both front ends below
  api.py                 FastAPI REST API (build your own app on top)
  bot/
    telegram_bot.py      Telegram bot (commands + daily digest + auto value-bet scan)
    formatting.py        pure text formatters (Telegram HTML), unit-testable
    notifications.py     pure dedup logic for the auto-scan, unit-testable
scripts/                 CLI entry points (see Usage above)
tests/                   unit tests (pytest) + tests/fixtures (cached sample HTML)
.github/workflows/       scheduled data/model refresh
Dockerfile               image used by all three docker-compose.yml services
docker-compose.yml       bot + api + auto-updater, sharing one data volume
docker/update_loop.sh    runs scripts/update_data.py once, then every 24h
quickstart.sh / .ps1     interactive setup wizard (writes config/.env, starts compose)
ANLEITUNG.md             beginner-oriented walkthrough (German)
```
