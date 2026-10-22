#!/usr/bin/env python3
"""Closing-line value and results for everything the dashboard logged.

    python scripts/report_clv.py              # CLV from the snapshot log
    python scripts/report_clv.py --results    # also fetch results and settle

This is the professional's scorecard. A bettor cannot tell from a week of
results whether an edge exists -- variance swamps it -- but the market's
closing price settles the question match by match: a price taken above the
sharp close has value whether or not the bet won. Every pick the dashboard
logged (data/processed/picks_log.csv) is held against the last quote of its
reference venue before the start (data/processed/odds_snapshots.csv).

With --results the finished matches' scores are read from TennisExplorer's
past-day pages and each pick is settled at the odds it was logged at.
"""
import _bootstrap  # noqa: F401
import argparse
import time

import pandas as pd

from tennissharp import config, market_compare as mc
from tennissharp.data import tennisexplorer as te


def closing_pairs(snapshots: pd.DataFrame) -> dict:
    """{(match_id, venue) -> ([odds1, odds2], taken_at)} -- the last quote per
    venue taken before the match started (or the last one at all when the
    start time is unknown)."""
    out = {}
    if snapshots.empty:
        return out
    snaps = snapshots.copy()
    snaps["start"] = pd.to_datetime(snaps["start_time"], utc=True, errors="coerce")
    pre = snaps[snaps["start"].isna() | (snaps["taken_at"] <= snaps["start"])]
    pre = pre.sort_values("taken_at")
    for (mid, venue), grp in pre.groupby(["match_id", "venue"]):
        last = grp.iloc[-1]
        out[(str(mid), venue)] = ([last["odds1"], last["odds2"]], last["taken_at"])
    return out


def attach_clv(picks: pd.DataFrame, snapshots: pd.DataFrame) -> pd.DataFrame:
    """One row per pick with the closing fair probability of its side and
    the CLV at the logged odds. Pinnacle's close is used where it exists,
    the pick's own reference venue otherwise."""
    closes = closing_pairs(snapshots)
    rows = []
    for p in picks.itertuples(index=False):
        mid = str(p.match_id)
        pair = closes.get((mid, "Pinnacle")) or closes.get((mid, p.ref_book))
        close_venue = "Pinnacle" if (mid, "Pinnacle") in closes else p.ref_book
        clv = None
        if pair:
            odds, _ = pair
            snap = snapshots[(snapshots["match_id"].astype(str) == mid)].iloc[0]
            side = 0 if str(snap["player1"]) == str(p.player) else 1
            ordered = [odds[side], odds[1 - side]]
            clv = mc.closing_value(float(p.odds), ordered)
        rows.append({**p._asdict(), "close_venue": close_venue if pair else None,
                     "clv": None if clv is None else round(clv, 4)})
    return pd.DataFrame(rows)


def fetch_results(days_back: int = 3) -> pd.DataFrame:
    frames = []
    for d in range(-days_back, 1):
        try:
            frames.append(te.fetch_matches(d))
        except Exception:
            continue
        time.sleep(1.0)
    if not frames:
        return pd.DataFrame()
    res = pd.concat(frames, ignore_index=True)
    res = res[res["sets_won1"].notna() & res["sets_won2"].notna()]
    return res.drop_duplicates(subset="match_id", keep="last")


def settle(picks: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """Profit per unit stake at the logged odds for picks whose match is decided."""
    if results.empty:
        picks["won"], picks["profit"] = None, None
        return picks
    by_id = {str(r.match_id): r for r in results.itertuples(index=False)}
    won, profit = [], []
    for p in picks.itertuples(index=False):
        r = by_id.get(str(p.match_id))
        if r is None or r.sets_won1 == r.sets_won2:
            won.append(None); profit.append(None); continue
        winner = r.player1 if r.sets_won1 > r.sets_won2 else r.player2
        hit = mc.name_matches(str(p.player), str(winner)) or str(p.player) == str(winner)
        won.append(bool(hit))
        profit.append(round(float(p.odds) - 1.0, 4) if hit else -1.0)
    picks["won"], picks["profit"] = won, profit
    return picks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", action="store_true", help="fetch recent results and settle")
    ap.add_argument("--days-back", type=int, default=3)
    args = ap.parse_args()

    picks_path = config.PROCESSED_DIR / "picks_log.csv"
    if not picks_path.exists():
        raise SystemExit("Noch keine Picks geloggt (data/processed/picks_log.csv fehlt).")
    picks = pd.read_csv(picks_path, dtype={"match_id": str})
    # The first time a side was logged is the price a follower would have had.
    picks = (picks.sort_values("taken_at")
                  .drop_duplicates(subset=["match_id", "player", "venue", "source"], keep="first"))
    snaps = mc.load_snapshots(config.PROCESSED_DIR / "odds_snapshots.csv")
    out = attach_clv(picks, snaps)
    if args.results:
        out = settle(out, fetch_results(args.days_back))

    pd.set_option("display.width", 200)
    print(f"{len(out)} Picks, {out['clv'].notna().sum()} mit Schlusskurs")
    have = out[out["clv"].notna()]
    if not have.empty:
        summary = (have.groupby(["source", "kind"])
                       .agg(n=("clv", "size"), clv_mean=("clv", "mean"),
                            clv_pos=("clv", lambda s: (s > 0).mean()))
                       .round(4))
        print("\nCLV nach Quelle:\n", summary.to_string())
    if "profit" in out.columns and out["profit"].notna().any():
        done = out[out["profit"].notna()]
        print(f"\nAbgerechnet: {len(done)} Picks, Treffer {done['won'].mean():.0%}, "
              f"Ergebnis {done['profit'].sum():+.2f} Einheiten "
              f"(ROI {done['profit'].mean():+.1%})")
    cols = [c for c in ("date", "tournament", "player", "venue", "source", "odds", "ev", "clv", "won", "profit")
            if c in out.columns]
    print("\n", out.sort_values("taken_at", ascending=False)[cols].head(25).to_string(index=False))
    out.to_csv(config.REPORTS_DIR / "clv_report.csv", index=False)


if __name__ == "__main__":
    main()
