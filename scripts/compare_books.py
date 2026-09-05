#!/usr/bin/env python3
"""Where does one bookmaker out-price another, right now?

    python scripts/compare_books.py                       # bet365 vs Pinnacle
    python scripts/compare_books.py --books Betfair Pinnacle
    python scripts/compare_books.py --all-books           # full price table

Pure market observation -- no model, no probability estimate. For every
scheduled match it reads each bookmaker's current price out of the
match-detail page and reports the sides where your book beats the sharp
reference.

Worth knowing before reading the output: a sharp book runs a much thinner
margin than a soft one (measured on a Cincinnati match: Betfair 3.1%,
bet365 5.4%, BetVictor 8.3%), so the sharp book is usually the better price
on BOTH sides. Where a soft book does go higher it is normally because the
sharp book has moved on new information and the soft one has not repriced
yet -- which is a real but perishable opportunity, not a standing one.

A price beating the reference's *offered* odds is not automatically +EV: the
reference includes its own margin. The `vs_fair` column is the stricter
test -- your price against the reference's de-vigged fair value, which is
what has to be beaten to make money.
"""
import _bootstrap  # noqa: F401
import argparse
import importlib.util
from pathlib import Path

import pandas as pd

from tennissharp import config, odds_math
from tennissharp.data import tennisexplorer as te

_spec = importlib.util.spec_from_file_location(
    "analyze_match", Path(__file__).parent / "analyze_match.py")
_am = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_am)
resolve_name = _am.resolve_name

SKIP_EVENTS = "UTR|Nationalliga|ITF"


def _current_prices(match_id) -> pd.DataFrame | None:
    """Latest quote per (bookmaker, player) for one match."""
    try:
        hist = te.fetch_match_odds_history(match_id)
    except Exception:
        return None
    if hist.empty:
        return None
    return hist.sort_values("timestamp").groupby(["bookmaker", "player"]).last().reset_index()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--books", nargs=2, default=["bet365", "Pinnacle"],
                   metavar=("YOURS", "REFERENCE"))
    p.add_argument("--limit", type=int, default=40, help="max matches to check")
    p.add_argument("--all-books", action="store_true",
                   help="also print the full per-book table for each match")
    p.add_argument("--fallback-sharpest", action="store_true",
                   help="when the reference book has no price for a match, use "
                        "the lowest-margin book present instead. TennisExplorer's "
                        "Pinnacle coverage is patchy (1 match in 6 in an evening "
                        "sample), so without this most matches drop out.")
    args = p.parse_args()
    mine, ref = args.books

    sched = pd.read_csv(config.PROCESSED_DIR / "tennisexplorer_upcoming.csv")
    sched = sched[~sched["tournament"].str.contains(SKIP_EVENTS, na=False, regex=True)]
    sched = sched[sched["odds1"].notna()].head(args.limit)

    rows, no_ref, no_mine = [], 0, 0
    for _, m in sched.iterrows():
        cur = _current_prices(m["match_id"])
        if cur is None:
            continue
        books = set(cur["bookmaker"])
        if mine not in books:
            no_mine += 1
            continue

        players = sorted(cur["player"].unique())
        if len(players) != 2:
            continue

        ref_used = ref
        if ref not in books:
            no_ref += 1
            if not args.fallback_sharpest:
                continue
            # Lowest margin among books quoting both sides -- the best
            # available stand-in for a sharp reference.
            best, best_margin = None, None
            for book in books:
                quotes = cur[cur["bookmaker"] == book]
                if len(quotes) != 2:
                    continue
                margin = sum(1.0 / q for q in quotes["odds"]) - 1.0
                if best_margin is None or margin < best_margin:
                    best, best_margin = book, margin
            if best is None or best == mine:
                continue
            ref_used = best

        def price(book, player):
            hit = cur[(cur["bookmaker"] == book) & (cur["player"] == player)]
            return float(hit["odds"].iloc[0]) if len(hit) else None

        ref_prices = [price(ref_used, pl) for pl in players]
        my_prices = [price(mine, pl) for pl in players]
        if None in ref_prices or None in my_prices:
            continue

        fair = odds_math.shin_devig(ref_prices)
        for pl, rp, mp_, fp in zip(players, ref_prices, my_prices, fair):
            rows.append({
                "match": f"{m['player1']} v {m['player2']}"[:34],
                "turnier": str(m["tournament"])[:20],
                "pick": pl[:22],
                "referenz": ref_used,
                mine: mp_, "ref_quote": rp,
                # How much better (or worse) your price is than the sharp
                # book's *offered* price -- the headline comparison.
                "diff": mp_ / rp - 1.0,
                # The stricter test: your price against the sharp book's
                # de-vigged fair value. Positive means genuinely +EV if you
                # take the reference's implied probability as truth.
                "vs_fair": mp_ * fp - 1.0,
            })

        if args.all_books:
            piv = cur.pivot(index="bookmaker", columns="player", values="odds")
            piv["marge"] = (1 / piv.iloc[:, 0] + 1 / piv.iloc[:, 1] - 1)
            print(f"\n--- {m['player1']} v {m['player2']} ({m['tournament']}) ---")
            print(piv.sort_values("marge").to_string())

    if not rows:
        raise SystemExit(f"\nKeine Partie mit Preisen von {mine} UND {ref} gefunden.\n"
                         f"({ref} fehlte bei {no_ref}, {mine} bei {no_mine} Partien.)")

    df = pd.DataFrame(rows).sort_values("diff", ascending=False)
    higher = df[df["diff"] > 0]
    beats_fair = df[df["vs_fair"] > 0]

    print(f"\n{len(df) // 2} Partien verglichen | {mine} vs {ref}")
    print(f"({ref} fehlte bei {no_ref} Partien, {mine} bei {no_mine})")
    print("=" * 88)

    print(f"\n{mine.upper()} HOEHER ALS {ref.upper()}:  {len(higher)} von {len(df)} Seiten"
          f"  ({len(higher) / len(df):.0%})")
    if higher.empty:
        print(f"  keine -- {ref} ist auf jeder Seite der bessere Preis.")
    else:
        for _, r in higher.iterrows():
            mark = "  +EV" if r["vs_fair"] > 0 else "      "
            ref_name, ref_q = r["referenz"], r["ref_quote"]
            print(f"{mark}  {r['pick']:22} {mine} {r[mine]:5.2f} vs {ref_name} {ref_q:5.2f}"
                  f"  ({r['diff']:+5.1%})  vs_fair {r['vs_fair']:+6.2%}   [{r['turnier']}]")

    print(f"\nSCHLAEGT {ref.upper()}S FAIRWERT (nach Abzug von {ref}s Marge): "
          f"{len(beats_fair)} von {len(df)}")
    if beats_fair.empty:
        print("  keine. Das ist der Normalfall -- siehe Modulkommentar.")

    print(f"\nDurchschnitt: {mine} liegt {df['diff'].mean():+.2%} gegenueber {ref}, "
          f"Median {df['diff'].median():+.2%}")
    print(f"Beste Seite:  {df.iloc[0]['pick']} {df.iloc[0]['diff']:+.1%}   "
          f"Schlechteste: {df.iloc[-1]['pick']} {df.iloc[-1]['diff']:+.1%}\n")

    show = df.head(15).copy()
    for c in ("diff", "vs_fair"):
        show[c] = show[c].map("{:+.2%}".format)
    print(show[["turnier", "pick", "referenz", mine, "ref_quote", "diff", "vs_fair"]].to_string(index=False))


if __name__ == "__main__":
    main()
