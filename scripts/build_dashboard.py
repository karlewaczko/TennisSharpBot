#!/usr/bin/env python3
"""Build the JSON payload behind the live value dashboard.

    python scripts/build_dashboard.py -o data/dashboard.json

For every scheduled match it records the market price, Pinnacle's price
where available, the model's probability, the implied fair odds and the
resulting edge -- everything the dashboard renders, computed here rather
than in the page, so the numbers are auditable from the command line.

Pinnacle coverage on TennisExplorer is partial (it appeared in roughly one
match in six in an evening sample). Rather than dropping those matches or
quietly substituting another book, each row carries `ref_book` naming the
book actually used as the sharp reference, and the dashboard shows it.

Matches where either player is below MIN_MATCHES_PLAYED are excluded from
the value table and counted separately: an unrated player sits at the
default 1500 Elo, which manufactures a large fake edge -- the most
attractive-looking and least real signal this model can produce.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from tennissharp import config, odds_math
from tennissharp.backtest import DEFAULT_EDGE_THRESHOLD, MIN_MATCHES_PLAYED
from tennissharp.data import tennisexplorer as te
from tennissharp.model import feature_columns
from tennissharp.value_finder import _features_for_matchup

_spec = importlib.util.spec_from_file_location(
    "analyze_match", Path(__file__).parent / "analyze_match.py")
_am = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_am)
resolve_name = _am.resolve_name

SKIP_EVENTS = "UTR|Nationalliga"
# Main-tour events first: the model is trained on tour-level match history,
# so its Elo is thin-to-absent for challenger and ITF fields (on this card
# 33 of 38 skipped matches were one challenger event). Ordering by tier
# means a capped run spends its budget where the model actually has data.
TIER_PRIORITY = ("Cincinnati", "Toronto", "Montreal", "Winston", "Cleveland",
                 "Washington", "Memphis")
SHARP_BOOKS = ("Pinnacle", "Betfair")


def _sharp_reference(match_id):
    """(book, [odds_a, odds_b], players) from the sharpest book quoting this
    match, preferring Pinnacle, then Betfair, then lowest margin."""
    try:
        hist = te.fetch_match_odds_history(match_id)
    except Exception:
        return None
    if hist.empty:
        return None
    cur = hist.sort_values("timestamp").groupby(["bookmaker", "player"]).last().reset_index()
    players = sorted(cur["player"].unique())
    if len(players) != 2:
        return None

    def quotes(book):
        rows = [cur[(cur["bookmaker"] == book) & (cur["player"] == pl)] for pl in players]
        if any(len(r) == 0 for r in rows):
            return None
        return [float(r["odds"].iloc[0]) for r in rows]

    for book in SHARP_BOOKS:
        q = quotes(book)
        if q:
            return book, q, players

    best, best_q, best_margin = None, None, None
    for book in cur["bookmaker"].unique():
        q = quotes(book)
        if not q:
            continue
        margin = sum(1 / x for x in q) - 1
        if best_margin is None or margin < best_margin:
            best, best_q, best_margin = book, q, margin
    return (best, best_q, players) if best else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", type=Path, default=config.PROCESSED_DIR / "dashboard.json")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--threshold", type=float, default=DEFAULT_EDGE_THRESHOLD)
    args = ap.parse_args()

    sched = pd.read_csv(config.PROCESSED_DIR / "tennisexplorer_upcoming.csv")
    sched = sched[~sched["tournament"].str.contains(SKIP_EVENTS, na=False, regex=True)]
    sched = sched[sched["odds1"].notna() & sched["odds2"].notna()]

    def tier_rank(name: str) -> int:
        for i, key in enumerate(TIER_PRIORITY):
            if key.lower() in str(name).lower():
                return i
        return len(TIER_PRIORITY) + (1 if "challenger" in str(name).lower() else 0)

    sched = (sched.assign(_tier=sched["tournament"].map(tier_rank))
                  .sort_values("_tier")
                  .drop(columns="_tier")
                  .head(args.limit))

    state = joblib.load(config.MODELS_DIR / "live_state.joblib")
    model = joblib.load(config.MODELS_DIR / "win_probability_model.joblib")
    snapshot = state.elo.snapshot()
    roster = snapshot["player"].tolist()
    played = dict(zip(snapshot["player"], snapshot["matches_played"]))
    elo_overall = dict(zip(snapshot["player"], snapshot["elo_overall"]))

    matches, skipped = [], []
    for _, m in sched.iterrows():
        a = resolve_name(str(m["player1"]), roster, weight=played.get)
        b = resolve_name(str(m["player2"]), roster, weight=played.get)
        label = f"{m['player1']} vs {m['player2']}"
        if not a or not b or a == b:
            skipped.append({"match": label, "tournament": str(m["tournament"]),
                            "reason": "Spieler nicht im Modell"})
            continue
        if min(played.get(a, 0), played.get(b, 0)) < MIN_MATCHES_PLAYED:
            thin = a if played.get(a, 0) < played.get(b, 0) else b
            skipped.append({"match": label, "tournament": str(m["tournament"]),
                            "reason": f"{thin}: nur {played.get(thin, 0):.0f} Matches"})
            continue

        ref = _sharp_reference(m["match_id"])
        if ref is None:
            ref_book, ref_odds = "TennisExplorer", [float(m["odds1"]), float(m["odds2"])]
            ref_players = [str(m["player1"]), str(m["player2"])]
        else:
            ref_book, ref_odds, ref_players = ref

        # Orient the reference prices onto (a, b).
        first = resolve_name(ref_players[0], [a, b])
        if first == b:
            ref_odds = [ref_odds[1], ref_odds[0]]

        fair_a, fair_b = odds_math.shin_devig(ref_odds)
        feats = _features_for_matchup(state, a, b, "Hard", 3, 1.0)
        clipped = float(np.clip(fair_a, 1e-6, 1 - 1e-6))
        feats["market_logit"] = float(np.log(clipped / (1 - clipped)))
        p_a = float(model.predict_proba(pd.DataFrame([feats])[feature_columns(True)])[0][1])

        sides = []
        for name, prob, fair, ref_price in ((a, p_a, fair_a, ref_odds[0]),
                                             (b, 1 - p_a, fair_b, ref_odds[1])):
            sides.append({
                "player": name,
                "model_prob": round(prob, 4),
                "model_fair_odds": round(1 / prob, 3) if prob > 0 else None,
                "market_prob": round(fair, 4),
                "market_fair_odds": round(1 / fair, 3) if fair > 0 else None,
                "ref_odds": round(ref_price, 3),
                "edge": round(odds_math.edge(prob, fair), 4),
                "ev_at_ref": round(prob * ref_price - 1, 4),
                "elo": round(float(elo_overall.get(name, float("nan"))), 1),
                "matches": int(played.get(name, 0)),
            })

        matches.append({
            "match_id": str(m["match_id"]),
            "tournament": str(m["tournament"]),
            "tour": "wta" if "-women/" in str(m["tournament_url"]) else "atp",
            "ref_book": ref_book,
            "ref_margin": round(sum(1 / x for x in ref_odds) - 1, 4),
            "sides": sides,
            "best_edge": round(max(s["edge"] for s in sides), 4),
            "signal": max(s["edge"] for s in sides) > args.threshold,
        })

    matches.sort(key=lambda x: x["best_edge"], reverse=True)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "threshold": args.threshold,
        "n_scheduled": int(len(sched)),
        "n_scored": len(matches),
        "n_signals": sum(1 for m in matches if m["signal"]),
        "ref_books": {b: sum(1 for m in matches if m["ref_book"] == b)
                      for b in sorted({m["ref_book"] for m in matches})},
        "matches": matches,
        "skipped": skipped,
        # Carried into the page so the dashboard cannot be read as a
        # profitability claim -- these are this repo's own audit numbers.
        "audit": {
            "information_gain": -0.00078,
            "matches_tested": 55124,
            "backtest_roi": 0.0135,
            "backtest_t": 0.48,
            "backtest_n": 1898,
        },
    }
    args.out.write_text(json.dumps(payload, indent=1))
    print(f"{payload['n_scored']} Partien bewertet, {payload['n_signals']} Signale, "
          f"{len(skipped)} uebersprungen -> {args.out}")
    print("Referenzbuecher:", payload["ref_books"])


if __name__ == "__main__":
    main()
