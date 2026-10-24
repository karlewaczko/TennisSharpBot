#!/usr/bin/env python3
"""Score a card of odds you can actually bet, priced against Pinnacle.

    python scripts/score_odds.py data/bet365_card.csv

Input CSV: player1,player2,odds1,odds2,event -- odds1/odds2 are the price
YOU can get (e.g. read off bet365), player names in any of the spellings the
project's sources use.

Why this is not just scan_value.py with different numbers: the model is
trained with the *sharp* book's de-vigged price as a feature, so the
reference price and the price you bet at must come from different books.
De-vigging your own bookmaker and then measuring "edge" against that same
bookmaker compares a book to itself and yields noise dressed as signal --
backtest.py refuses that combination outright, and this script keeps the
same rule.

So for every match it pulls Pinnacle's *current* price from the match-detail
page (TennisExplorer embeds each bookmaker's live odds there), feeds
Pinnacle de-vigged into the model, and reports the edge at YOUR price.
Matches where Pinnacle has no price are reported, not silently scored
against a substitute.
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
from tennissharp.data import tennisexplorer as te
from tennissharp.model import feature_columns
from tennissharp.value_finder import _features_for_matchup

_spec = importlib.util.spec_from_file_location(
    "analyze_match", Path(__file__).parent / "analyze_match.py")
_am = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_am)
resolve_name = _am.resolve_name

REFERENCE_BOOK = "Pinnacle"

# German betting tax (Rennwett- und Lotteriegesetz): 5.3% of the STAKE, not
# of winnings, since GlueStV 2021.
#
# Whether it costs YOU anything depends on the operator: most pass it on, but
# bet365 has absorbed it since January 2024, as have Winamax and Neobet. So
# the default here is 0 -- bet365 is what this project's cards are read off.
# Pass --tax 0.053 for an operator that deducts it; it is worth checking,
# because it moves break-even further than any signal we have measured (at
# odds 1.37 the required hit rate goes from 73.0% to 77.1%).
DEFAULT_STAKE_TAX = 0.0

# Betting brokers (BetInAsia, Sportmarket, ...) charge commission on NET
# WINNINGS instead, typically 0.5-2%. That behaves quite differently from a
# stake tax: it is only paid on winning bets, so at a ~48% hit rate a 2%
# commission costs about 1.15 points of ROI, not 2. Set --commission 0 for a
# plain bookmaker account.
DEFAULT_COMMISSION = 0.0


def _pinnacle_prices(match_id, player_a, player_b) -> tuple[float, float] | None:
    """Pinnacle's latest quote for both sides, or None if it isn't priced."""
    try:
        hist = te.fetch_match_odds_history(match_id)
    except Exception:
        return None
    if hist.empty or REFERENCE_BOOK not in set(hist["bookmaker"]):
        return None
    pin = hist[hist["bookmaker"] == REFERENCE_BOOK].sort_values("timestamp")
    latest = pin.groupby("player").last()["odds"]
    a = resolve_name(player_a, list(latest.index))
    b = resolve_name(player_b, list(latest.index))
    if not a or not b or a == b:
        return None
    return float(latest[a]), float(latest[b])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("card", type=Path)
    p.add_argument("--threshold", type=float, default=DEFAULT_EDGE_THRESHOLD)
    p.add_argument("--surface", default="Hard")
    p.add_argument("--commission", type=float, default=DEFAULT_COMMISSION,
                   help="broker commission on net winnings, e.g. 0.02 for "
                        "BetInAsia. Applied only to winning bets.")
    p.add_argument("--tax", type=float, default=DEFAULT_STAKE_TAX,
                   help="stake tax as a fraction. Default 0: bet365/Winamax/Neobet absorb it. Pass 0.053 for a German operator that deducts it.")
    args = p.parse_args()

    card = pd.read_csv(args.card)
    sched = pd.read_csv(config.PROCESSED_DIR / "tennisexplorer_upcoming.csv")
    state = joblib.load(config.MODELS_DIR / "live_state.joblib")
    model = joblib.load(config.MODELS_DIR / "win_probability_model.joblib")
    snapshot = state.elo.snapshot()
    roster = snapshot["player"].tolist()
    played = dict(zip(snapshot["player"], snapshot["matches_played"]))

    scored, problems = [], []
    for _, row in card.iterrows():
        q1, q2, event = str(row["player1"]), str(row["player2"]), row.get("event", "")
        a = resolve_name(q1, roster)
        b = resolve_name(q2, roster)
        if not a or not b or a == b:
            missing = q1 if not a else q2
            problems.append((q1, q2, event, f"{missing}: nicht im Modell"))
            continue
        if min(played.get(a, 0), played.get(b, 0)) < MIN_MATCHES_PLAYED:
            thin = a if played.get(a, 0) < played.get(b, 0) else b
            problems.append((q1, q2, event, f"{thin}: nur {played.get(thin, 0):.0f} Matches"))
            continue

        # Find the match in the schedule to get its match_id for Pinnacle.
        hit = None
        for _, m in sched.iterrows():
            s1 = resolve_name(str(m["player1"]), [a, b])
            s2 = resolve_name(str(m["player2"]), [a, b])
            if s1 and s2 and s1 != s2:
                hit = (m, s1 == a)
                break
        if hit is None:
            problems.append((q1, q2, event, "nicht im Spielplan -- kein Pinnacle-Preis"))
            continue

        m, same_order = hit
        pin = _pinnacle_prices(m["match_id"], a, b)
        if pin is None:
            problems.append((q1, q2, event, f"{REFERENCE_BOOK} hat keinen Preis"))
            continue
        pin_a, pin_b = pin

        fair_a, fair_b = odds_math.shin_devig([pin_a, pin_b])
        feats = _features_for_matchup(state, a, b, args.surface, 3, 1.0)
        clipped = float(np.clip(fair_a, 1e-6, 1 - 1e-6))
        feats["market_logit"] = float(np.log(clipped / (1 - clipped)))
        model_p = float(model.predict_proba(pd.DataFrame([feats])[feature_columns(True)])[0][1])

        my_a, my_b = float(row["odds1"]), float(row["odds2"])
        for name, mp, fp, price, pinp, opp in (
            (a, model_p, fair_a, my_a, pin_a, b),
            (b, 1 - model_p, fair_b, my_b, pin_b, a),
        ):
            scored.append({
                "event": event, "pick": name, "gegen": opp,
                "dein_preis": price, "pinnacle": pinp,
                "modell": mp, "pin_fair": fp,
                "edge": odds_math.edge(mp, fp),
                # THE decision number: expected value at the price you can
                # actually take. "edge" measures the model against Pinnacle's
                # *fair* (de-vigged) price, which nobody offers -- a bet can
                # clear the edge threshold and still be -EV once your book's
                # margin is paid. Always read this column before betting.
                # Stake tax is levied on the stake, so only (1-tax) is
                # actually at risk: payout per 1.0 staked is price*(1-tax).
                # Stake tax hits the stake; broker commission hits only the
                # profit on winning bets. Net EV per 1.0 staked:
                #   win  -> (price*(1-tax) - 1) * (1-commission)
                #   lose -> -1
                "ev_dein_preis": (mp * ((price * (1 - args.tax) - 1.0) * (1 - args.commission))
                                   - (1 - mp)),
                "ev_ohne_steuer": mp * price - 1.0,
                # Does your book price this side better than the sharp book's
                # fair value? A market observation, independent of the model.
                "preisvorteil": price * fp - 1.0,
            })

    df = pd.DataFrame(scored)
    print(f"\n{len(card)} Partien eingelesen, {len(df) // 2 if len(df) else 0} bewertet"
          f" | Referenz: {REFERENCE_BOOK}, Schwelle {args.threshold:.0%}"
          f", Steuer {args.tax:.1%}, Kommission {args.commission:.1%}\n" + "=" * 84)

    if not df.empty:
        hits = df[df["edge"] > args.threshold].sort_values("edge", ascending=False)
        print(f"\nMODELL-SIGNALE (Edge > {args.threshold:.0%}):")
        if hits.empty:
            print("  keine.\n")
        else:
            for _, r in hits.iterrows():
                flag = "" if r["ev_dein_preis"] > 0 else "  <-- ABER -EV BEI DEINEM PREIS"
                print(f"  {r['pick']:22} vs {r['gegen']:20} @ {r['dein_preis']:5.2f}  "
                      f"Edge {r['edge']:+6.1%}  EV {r['ev_dein_preis']:+6.1%}"
                      f"   [{r['event']}]{flag}")
            print()

        actionable = df[df["ev_dein_preis"] > 0].sort_values("ev_dein_preis", ascending=False)
        print("POSITIVER EV ZU DEINEM PREIS (nach Steuer und Kommission):")
        if actionable.empty:
            print("  keine -- jede Seite ist zu deinem Preis negativ.\n")
        else:
            for _, r in actionable.head(8).iterrows():
                print(f"  {r['pick']:22} @ {r['dein_preis']:5.2f}  "
                      f"EV {r['ev_dein_preis']:+6.1%}   [{r['event']}]")
            print()

        price_hits = df[df["preisvorteil"] > 0].sort_values("preisvorteil", ascending=False)
        print(f"DEIN PREIS SCHLAEGT {REFERENCE_BOOK.upper()}S FAIRWERT "
              "(unabhaengig vom Modell):")
        if price_hits.empty:
            print(f"  keine -- {REFERENCE_BOOK} ist ueberall der bessere Preis.\n")
        else:
            for _, r in price_hits.head(8).iterrows():
                print(f"  {r['pick']:22} @ {r['dein_preis']:5.2f} vs {REFERENCE_BOOK} "
                      f"{r['pinnacle']:5.2f}  -> {r['preisvorteil']:+6.2%}   [{r['event']}]")
            print()

        show = df.sort_values("edge", ascending=False).head(12).copy()
        for c in ("modell", "pin_fair", "edge", "ev_ohne_steuer", "ev_dein_preis", "preisvorteil"):
            signed = c in ("edge", "ev_ohne_steuer", "ev_dein_preis", "preisvorteil")
            show[c] = show[c].map(lambda v, s=signed: f"{v:+.1%}" if s else f"{v:.1%}")
        print("Groesste Modellabweichungen:\n")
        print(show[["event", "pick", "dein_preis", "pinnacle", "modell", "pin_fair",
                    "edge", "ev_ohne_steuer", "ev_dein_preis"]].to_string(index=False))

    if problems:
        print(f"\nNicht bewertet ({len(problems)}):")
        for q1, q2, ev, why in problems:
            print(f"  {q1} vs {q2}  [{ev}] -- {why}")

    print("\n" + "-" * 84)
    print("audit_edge.py: kein Informationsvorsprung ggue. dem Markt (gain -0.00078).")
    print("'Edge' misst gegen Pinnacles FAIRWERT -- den bietet niemand an.")
    print("'ev_dein_preis' ist die Entscheidungsgroesse -- inkl. Wettsteuer.")
    print(f"Bei {DEFAULT_STAKE_TAX:.1%} Einsatzsteuer muss die Quote um {1/(1-DEFAULT_STAKE_TAX)-1:.1%}")
    print("hoeher liegen, nur um auf null zu kommen.")
    print("-" * 84 + "\n")


if __name__ == "__main__":
    main()
