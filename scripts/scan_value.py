#!/usr/bin/env python3
"""Score every scheduled match for value in one pass.

    python scripts/scan_value.py                       # everything scheduled
    python scripts/scan_value.py --tournament cincinnati cancun

Same maths as scripts/analyze_match.py, run over the cached TennisExplorer
schedule instead of one pairing, and printed as a table sorted by edge.

`--tournament` matches against the tournament URL, not the display name, so
"cincinnati" selects the ATP event without also pulling in Cincinnati WTA
(their URLs are .../cincinnati/... and .../cincinnati-wta/...).

Matches where either player is unknown to the model are listed separately
rather than skipped silently: an unrated player sits at the default 1500
Elo, which manufactures a large fake edge against the market, and that is
exactly the kind of "signal" that looks best and is worth least.
"""
import _bootstrap  # noqa: F401
import argparse
import importlib.util
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from tennissharp import config, odds_math
from tennissharp.backtest import DEFAULT_EDGE_THRESHOLD, MIN_MATCHES_PLAYED
from tennissharp.model import feature_columns
from tennissharp.value_finder import _features_for_matchup

_spec = importlib.util.spec_from_file_location(
    "analyze_match", Path(__file__).parent / "analyze_match.py")
_am = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_am)
resolve_name = _am.resolve_name


def _surface_for(tournament_url: str, speed_df: pd.DataFrame | None) -> tuple[str, float]:
    """Guess surface + speed from the tournament name. Hard is the right
    default for the current (August) swing; a wrong guess only shifts the
    surface-Elo term, it does not invent a price."""
    surface, speed = "Hard", 1.0
    if speed_df is not None and not speed_df.empty:
        from tennissharp.tourney_matching import normalize_tourney_name
        key = normalize_tourney_name(tournament_url.rstrip("/").split("/")[-3])
        hits = speed_df[speed_df["tournament"].apply(
            lambda t: normalize_tourney_name(t) == key)]
        if not hits.empty:
            row = hits.sort_values("date").iloc[-1]
            surface, speed = str(row["surface"]), float(row["surface_speed"])
    return surface, speed


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tournament", nargs="*", default=None,
                   help="substrings matched against the tournament URL")
    p.add_argument("--threshold", type=float, default=DEFAULT_EDGE_THRESHOLD)
    args = p.parse_args()

    sched = pd.read_csv(config.PROCESSED_DIR / "tennisexplorer_upcoming.csv")
    if args.tournament:
        mask = pd.Series(False, index=sched.index)
        for frag in args.tournament:
            mask |= sched["tournament_url"].str.contains(frag, case=False, na=False)
        sched = sched[mask]
    sched = sched[sched["odds1"].notna() & sched["odds2"].notna()]
    if sched.empty:
        raise SystemExit("Keine Partien mit Quoten gefunden.")

    state = joblib.load(config.MODELS_DIR / "live_state.joblib")
    model = joblib.load(config.MODELS_DIR / "win_probability_model.joblib")
    snapshot = state.elo.snapshot()
    roster = snapshot["player"].tolist()
    played = dict(zip(snapshot["player"], snapshot["matches_played"]))

    speed_path = config.PROCESSED_DIR / "ta_surface_speed_history.csv"
    speed_df = pd.read_csv(speed_path, parse_dates=["date"]) if speed_path.exists() else None

    rows, skipped = [], []
    for _, m in sched.iterrows():
        a = resolve_name(str(m["player1"]), roster)
        b = resolve_name(str(m["player2"]), roster)
        if not a or not b or a == b:
            skipped.append((m["player1"], m["player2"], m["tournament"], "unbekannt im Modell"))
            continue
        if min(played.get(a, 0), played.get(b, 0)) < MIN_MATCHES_PLAYED:
            thin = a if played.get(a, 0) < played.get(b, 0) else b
            skipped.append((m["player1"], m["player2"], m["tournament"],
                            f"{thin}: nur {played.get(thin, 0):.0f} Matches"))
            continue

        surface, speed = _surface_for(str(m["tournament_url"]), speed_df)
        fair_a, fair_b = odds_math.shin_devig([float(m["odds1"]), float(m["odds2"])])
        feats = _features_for_matchup(state, a, b, surface, 3, speed)
        clipped = float(np.clip(fair_a, 1e-6, 1 - 1e-6))
        feats["market_logit"] = float(np.log(clipped / (1 - clipped)))
        model_p = float(model.predict_proba(pd.DataFrame([feats])[feature_columns(True)])[0][1])

        for name, mp, fp, price, opp in ((a, model_p, fair_a, m["odds1"], b),
                                          (b, 1 - model_p, fair_b, m["odds2"], a)):
            rows.append({
                "Turnier": m["tournament"], "Belag": surface,
                "Wette auf": name, "gegen": opp, "Quote": float(price),
                "Modell": mp, "Markt fair": fp,
                "Edge": odds_math.edge(mp, fp),
            })

    df = pd.DataFrame(rows).sort_values("Edge", ascending=False)
    hits = df[df["Edge"] > args.threshold]

    print(f"\n{len(sched)} Partien geprueft, Schwelle {args.threshold:.0%}\n" + "=" * 78)
    if hits.empty:
        print(f"\nKEIN SIGNAL: keine Seite erreicht {args.threshold:.0%} Edge.\n")
    else:
        print(f"\n{len(hits)} Signal(e):\n")
        for _, r in hits.iterrows():
            print(f"  {r['Wette auf']:24} vs {r['gegen']:22} @ {r['Quote']:5.2f}  "
                  f"Edge {r['Edge']:+6.1%}  (Modell {r['Modell']:.1%} / Markt {r['Markt fair']:.1%})")
        print()

    print("Groesste Abweichungen Modell vs Markt (auch unter der Schwelle):\n")
    show = df.head(10).copy()
    for col in ("Modell", "Markt fair", "Edge"):
        show[col] = show[col].map(lambda v: f"{v:+.1%}" if col == "Edge" else f"{v:.1%}")
    print(show.to_string(index=False))

    if skipped:
        print(f"\nUebersprungen ({len(skipped)}) -- zu wenig Historie, Elo waere geraten:")
        for p1, p2, t, why in skipped:
            print(f"  {p1} vs {p2}  [{t}] -- {why}")

    print("\n" + "-" * 78)
    print("audit_edge.py: keine Information ueber den Markt hinaus (gain -0.00078).")
    print("Ein Signal hier ist eine Modellabweichung, kein belegter Vorteil.")
    print("-" * 78 + "\n")


if __name__ == "__main__":
    main()
