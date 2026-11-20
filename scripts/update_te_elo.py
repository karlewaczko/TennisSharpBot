#!/usr/bin/env python3
"""Our Elo for every TennisExplorer player (src/tennissharp/te_elo.py).

    python scripts/update_te_elo.py --rebuild --days 730   # from scratch, with a backtest
    python scripts/update_te_elo.py                         # add the days since the last run

A rebuild reads `--days` result pages (one request each, about two
seconds; pages are cached in data/raw/te_results/), learns the newcomers'
starting ratings per level, plays every result in order and scores the
forecasts of the last `--test-days` against the results and the market.
The daily run reads data/processed/te_elo_current.csv, fetches the days
after its `through` date up to yesterday and plays them on.

Writes data/processed/te_elo_current.csv and te_elo_meta.json, and on a
rebuild data/reports/te_elo_backtest.json.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import json
import time

import pandas as pd

from tennissharp import config
from tennissharp import te_elo
from tennissharp.data import tennisexplorer as te

CACHE = config.RAW_DIR / "te_results"
TABLE = config.PROCESSED_DIR / "te_elo_current.csv"
META = config.PROCESSED_DIR / "te_elo_meta.json"
REPORT = config.REPORTS_DIR / "te_elo_backtest.json"


def day_results(day: dt.date, today: dt.date, use_cache: bool = True) -> pd.DataFrame:
    """One day's finished singles, from the cache when the day is long over."""
    path = CACHE / f"{day.isoformat()}.csv"
    if use_cache and path.exists():
        raw = pd.read_csv(path, dtype={"match_id": str, "time": str})
    else:
        for attempt in range(4):
            try:
                raw = te.fetch_matches((day - today).days)
                break
            except Exception as exc:  # network hiccup: wait and retry
                if attempt == 3:
                    raise
                print(f"  {day}: {exc}; retrying", flush=True)
                time.sleep(5 * (attempt + 1))
        raw["date"] = day.isoformat()
        if (today - day).days >= 3:            # late results are in by then
            CACHE.mkdir(parents=True, exist_ok=True)
            raw.to_csv(path, index=False)
        time.sleep(0.5)
    return te_elo.results(raw)


def fetch_days(first: dt.date, last: dt.date, today: dt.date) -> pd.DataFrame:
    frames, day, n = [], first, (last - first).days + 1
    i = 0
    while day <= last:
        frames.append(day_results(day, today))
        i += 1
        if i % 25 == 0:
            print(f"  {i}/{n} Tage, bis {day}", flush=True)
        day += dt.timedelta(days=1)
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else te_elo.results(None)


def write(r: te_elo.Ratings, through: dt.date, start: dict, extra: dict | None = None) -> None:
    r.table().to_csv(TABLE, index=False)
    META.write_text(json.dumps({"through": through.isoformat(), "start": start,
                                "players": len(r.players), **(extra or {})}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--days", type=int, default=730)
    ap.add_argument("--test-days", type=int, default=90)
    args = ap.parse_args()
    today = dt.datetime.now(dt.timezone.utc).date()
    yesterday = today - dt.timedelta(days=1)

    if args.rebuild or not TABLE.exists():
        first = today - dt.timedelta(days=args.days)
        rows = fetch_days(first, yesterday, today)
        cut = (yesterday - dt.timedelta(days=args.test_days - 1)).isoformat()
        start = te_elo.level_start(rows[rows["date"] < cut])
        r = te_elo.Ratings(start)
        r.play(rows[rows["date"] < cut])
        record: list = []
        r.play(rows[rows["date"] >= cut], record)
        df = pd.DataFrame(record)
        report = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                  "days": args.days, "test_days": args.test_days, "matches": int(len(rows)),
                  "start": start, "all": te_elo.score(record),
                  "settled": te_elo.score([x for x in record if x["n_min"] >= te_elo.MIN_SURE]),
                  "by_level": {lv: te_elo.score(g.to_dict("records")) for lv, g in df.groupby("level")},
                  "by_matches": {lab: te_elo.score(df[(df.n_min >= lo) & (df.n_min < hi)].to_dict("records"))
                                 for lab, lo, hi in (("0-4", 0, 5), ("5-14", 5, 15), ("15-39", 15, 40),
                                                     ("40+", 40, 10 ** 9))}}
        REPORT.write_text(json.dumps(report, indent=1))
        write(r, yesterday, start, {"rebuilt": today.isoformat(), "days": args.days})
        print(json.dumps({k: report[k] for k in ("matches", "start", "all", "settled")}, indent=1))
        return

    meta = json.loads(META.read_text())
    through = dt.date.fromisoformat(meta["through"])
    if through >= yesterday:
        print(f"Elo schon bis {through}.")
        return
    r = te_elo.Ratings.from_table(pd.read_csv(TABLE, dtype={"slug": str}), meta.get("start"))
    rows = fetch_days(through + dt.timedelta(days=1), yesterday, today)
    r.play(rows)
    write(r, yesterday, meta.get("start") or {}, {k: v for k, v in meta.items()
                                                 if k not in ("through", "start", "players")})
    print(f"Elo bis {yesterday}: {len(rows)} Partien, {len(r.players)} Spieler.")


if __name__ == "__main__":
    main()
