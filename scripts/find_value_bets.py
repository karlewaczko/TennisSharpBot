#!/usr/bin/env python3
"""Compare live bookmaker odds against the model to flag value-bet candidates.

Requires ODDS_API_KEY (config/.env) and that scripts/update_data.py has been
run at least once so models/win_probability_model.joblib and
models/live_state.joblib exist.

This is a decision-support list, not an instruction to bet -- see the
disclaimer in README.md before acting on anything it prints.
"""
import _bootstrap  # noqa: F401
import argparse

import joblib

from tennissharp import config
from tennissharp.data import live_odds
from tennissharp.model import load as load_model
from tennissharp.value_finder import find_value_bets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edge-threshold", type=float, default=0.03)
    parser.add_argument("--kelly-fraction", type=float, default=0.25)
    parser.add_argument("--bankroll", type=float, default=10_000.0)
    parser.add_argument("--regions", default="eu")
    args = parser.parse_args()

    model_path = config.MODELS_DIR / "win_probability_model.joblib"
    state_path = config.MODELS_DIR / "live_state.joblib"
    if not model_path.exists() or not state_path.exists():
        raise SystemExit("Run scripts/update_data.py first to build the model and player-state files.")

    model = load_model(model_path)
    state = joblib.load(state_path)

    events = live_odds.fetch_all_active_tennis_odds(regions=args.regions)
    if not events:
        print("No active tennis events/odds returned by the API right now.")
        return

    bets = find_value_bets(
        state, model, events, edge_threshold=args.edge_threshold,
        kelly_fraction=args.kelly_fraction, bankroll=args.bankroll,
    )
    if bets.empty:
        print("No value bets found above the edge threshold.")
        return

    out_path = config.REPORTS_DIR / "value_bets_latest.csv"
    bets.to_csv(out_path, index=False)
    print(bets.to_string(index=False))
    print(f"\nSaved to {out_path}")
    print("\nReminder: this ranks candidates by modelled edge vs. the de-vigged market. "
          "It is not financial advice -- verify independently, mind German LUGAS deposit "
          "limits, and never stake more than you can afford to lose.")


if __name__ == "__main__":
    main()
