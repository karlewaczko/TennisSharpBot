#!/usr/bin/env python3
"""Run the full honesty audit: is there an edge here, or are we fooling ourselves?

Answers four questions, in the order that matters:
  1. Which odds columns are actually purchasable prices? (bad ones invent free money)
  2. Is the market we want to beat actually beatable? (calibration)
  3. Given the market price, do our features add anything? (the decisive test)
  4. If we bet, is the ROI distinguishable from zero? (t-stats, per segment)

Writes data/reports/edge_audit.md and prints a summary. Run this before
believing ANY backtest result -- including this repo's own.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt

import pandas as pd

from tennissharp import config, edge_audit
from tennissharp.features import FEATURE_COLUMNS, attach_market_probability, build_feature_table
from tennissharp.tourney_matching import load_surface_speed_index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-matches-played", type=int, default=10,
                        help="Skip players with fewer recorded matches (their Elo is meaningless)")
    args = parser.parse_args()

    cache = config.PROCESSED_DIR / "matches_normalized.csv"
    if not cache.exists():
        raise SystemExit("Run scripts/update_data.py first.")
    matches = pd.read_csv(cache, parse_dates=["date"])

    out = [f"# Edge audit ({dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')})", ""]
    print(f"Loaded {len(matches)} matches.\n")

    # --- 1. Which prices are real? ------------------------------------------
    print("=" * 72)
    print("1. PRICE ATTAINABILITY -- can you actually bet these numbers?")
    print("=" * 72)
    attain = edge_audit.price_attainability_report(matches)
    print(attain.to_string(index=False))
    print()
    out += ["## 1. Price attainability", "",
            "A price column implying a negative overround on a large share of matches "
            "is a running maximum over the market's lifetime, not a quotable price. "
            "Backtesting against it invents money that was never available.", "",
            attain.to_markdown(index=False), ""]

    unattainable = attain[~attain.attainable].price_column.tolist()
    if unattainable:
        print(f"  !! NOT ATTAINABLE: {', '.join(unattainable)} -- excluded from all bet pricing.\n")

    # --- 2. Is the market beatable? -----------------------------------------
    print("=" * 72)
    print("2. MARKET CALIBRATION -- is Pinnacle actually mispricing anything?")
    print("=" * 72)
    cal = edge_audit.market_calibration_report(matches)
    print(cal.to_string(index=False))
    worst = cal.error.abs().max() if not cal.empty else float("nan")
    print(f"\n  Largest gap between implied and realised win rate: {worst:.4f}")
    print("  (a well-calibrated market sits under ~0.01 across the range)\n")
    out += ["## 2. Market calibration", "",
            f"Largest gap between de-vigged implied probability and realised win rate: "
            f"**{worst:.4f}**.", "", cal.to_markdown(index=False), ""]

    # --- 3. The decisive test ------------------------------------------------
    print("=" * 72)
    print("3. INCREMENTAL INFORMATION -- given the market price, do we add anything?")
    print("=" * 72)
    print("  (training a model per season, this takes a couple of minutes)")
    speed_path = config.PROCESSED_DIR / "ta_surface_speed_history.csv"
    speed_index = load_surface_speed_index(speed_path, config.START_SEASON) if speed_path.exists() else None

    table, _ = build_feature_table(matches, surface_speed_index=speed_index)
    table = attach_market_probability(table)
    table = table[(table.player1_matches_played >= args.min_matches_played)
                  & (table.player2_matches_played >= args.min_matches_played)]

    report = edge_audit.incremental_information_test(table, FEATURE_COLUMNS)
    summary = edge_audit.summarize_incremental(report)
    print()
    if not report.empty:
        print(report.to_string(index=False))
    print()
    for k, v in summary.items():
        print(f"  {k:28s}: {v}")
    print()
    out += ["## 3. Incremental information over the market", "",
            "The decisive test. If a model trained on [market price + our features] "
            "cannot beat one trained on [market price] alone, out of sample, then we "
            "hold no information the market lacks -- and no amount of tuning creates an edge.",
            ""]
    if not report.empty:
        out += [report.to_markdown(index=False), ""]
    out += ["```", *[f"{k}: {v}" for k, v in summary.items()], "```", ""]

    # --- 4. Would betting have paid? ----------------------------------------
    print("=" * 72)
    print("4. STRATEGY ROI WITH SIGNIFICANCE -- attainable prices only")
    print("=" * 72)
    attainable_cols = set(attain[attain.attainable].price_column)
    long = _both_sides(matches)
    out += ["## 4. Strategy ROI, attainable prices only", ""]

    for price_label in ("bet365", "market_avg"):
        if price_label not in attainable_cols or f"{price_label}_price" not in long.columns:
            continue
        print(f"\n  Betting {price_label} whenever it beats Pinnacle's de-vigged fair price:")
        out += [f"### Betting `{price_label}` vs Pinnacle fair", "",
                "| EV threshold | n bets | ROI | t-stat | verdict |", "|---|---|---|---|---|"]
        price = long[f"{price_label}_price"]
        ev = long.fair * price - 1.0
        for thresh in (0.0, 0.02, 0.05):
            sel = long[ev > thresh]
            stats = edge_audit.roi_with_significance(
                sel.won.to_numpy(), sel[f"{price_label}_price"].to_numpy())
            if not stats["n_bets"]:
                continue
            print(f"    EV>{thresh:.2f}: n={stats['n_bets']:6d}  ROI={stats['roi']*100:+6.2f}%  "
                  f"t={stats['t_stat']:+5.2f}  -> {stats['interpretation']}")
            out.append(f"| >{thresh:.2f} | {stats['n_bets']} | {stats['roi']*100:+.2f}% | "
                       f"{stats['t_stat']:+.2f} | {stats['interpretation']} |")
        out.append("")

    report_path = config.REPORTS_DIR / "edge_audit.md"
    report_path.write_text("\n".join(out))
    print(f"\n\nFull report written to {report_path}")
    print("\n" + "=" * 72)
    print("BOTTOM LINE:", summary.get("verdict", "inconclusive"))
    print("=" * 72)


def _both_sides(matches: pd.DataFrame) -> pd.DataFrame:
    """One row per player-side, with the de-vigged Pinnacle fair probability
    for that side and each book's price for it."""
    need = ["pinnacle_w", "pinnacle_l"]
    d = matches.dropna(subset=need).copy()
    fair = [edge_audit.devig_pair(a, b) for a, b in zip(d.pinnacle_w, d.pinnacle_l)]
    fw = [f[0] for f in fair]
    fl = [f[1] for f in fair]

    frames = []
    for side, fair_vals, won in (("w", fw, 1), ("l", fl, 0)):
        frame = pd.DataFrame({"fair": fair_vals, "won": won,
                              "tour": d.tour.to_numpy(), "surface": d.surface.to_numpy(),
                              "tier": d.tier.to_numpy(), "date": d.date.to_numpy()})
        for label in ("bet365", "market_avg", "market_max"):
            col = f"{label}_{side}"
            if col in d.columns:
                frame[f"{label}_price"] = d[col].to_numpy()
        frames.append(frame)
    long = pd.concat(frames, ignore_index=True)
    return long.dropna(subset=["fair"])


if __name__ == "__main__":
    main()
