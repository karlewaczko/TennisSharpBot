"""Walk-forward historical backtest: train on the past, bet on the next
season, roll forward.

Three guardrails exist here because their absence is how backtests lie:

1. **Attainable prices only.** `market_max` is a running maximum over the
   market's lifetime (it implies cross-book arbitrage on ~43% of matches --
   see `edge_audit.price_attainability_report`). You cannot bet a price that
   existed briefly three days ago, so betting it here is refused outright
   rather than left as a footgun.
2. **The model is priced against a *different* book than the one it bets at.**
   The model is trained with the de-vigged market price as a feature, so
   scoring a bet at book X using X's own price compares X to itself.
   Pinnacle is the reference; bets are placed at a softer book.
3. **Every ROI comes with a t-statistic.** Tennis ROIs have huge variance:
   this repo's own audit produces a +69% ROI over 265 bets that is
   statistically indistinguishable from zero. An ROI without a standard
   error is a rumour.

On CLV: true closing-line value needs the price you bet *and* the market's
final closing price. This dataset has one snapshot per bookmaker per match,
so `mean_edge_vs_reference` is a stand-in, not literal CLV. Don't report it
as CLV.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tennissharp import edge_audit
from tennissharp import model as model_mod
from tennissharp import odds_math, staking
from tennissharp.features import attach_market_probability, build_feature_table

# Only bet when the model claims at least this much edge over the sharp
# reference price. Set to 0.05 on request. Measured on the 2015-2026 backtest
# (regenerate with scripts/run_backtest.py; per-bet rows land in
# data/reports/backtest_bets.csv):
#
#   threshold   n bets   ROI      t-stat   bets/yr   yrs to reach t=2
#   3%           8112    -1.81%   -1.36      738     never (ROI is negative)
#   5%           1898    +1.35%   +0.48      172     ~191
#   10%            51   +16.94%   +0.87      4.6      ~59
#
# ROI rising with the threshold is NOT evidence the filter works: the t-stat
# stays flat, so the move is smaller samples spreading wider, not signal. Note
# 5% needs *longer* to validate than 10% (191 vs 59 years) -- its ROI is much
# smaller relative to the same per-bet variance. Neither is reachable.
#
# The model's edge estimate also gets less accurate the larger it claims to be
# -- realised minus model-predicted win rate, by bucket:
#   edge 3-5%: -2.4pp | 5-7.5%: -2.9pp | 7.5-10%: -3.8pp | 10%+: -4.3pp
# Above the 5% cut the model claims +6.3pp over the market and delivers
# +3.3pp, overstating by ~1.9x. That is adverse selection: the bets where the
# model most disagrees with the market are the ones where the model, not the
# market, is most often wrong -- and raising the threshold selects harder for
# exactly those.
#
# Treat this as a risk control (bet fewer, higher-conviction spots), NOT as a
# profitability filter. scripts/audit_edge.py's verdict is unchanged:
# no information beyond the market (information gain -0.00078 over 55k
# matches), and every threshold above is "consistent with zero edge".
DEFAULT_EDGE_THRESHOLD = 0.05
# The book we place bets at. Must be a real, quotable price -- never market_max.
DEFAULT_BET_PRICE_COL = "market_avg"
# The sharp book we price *against*. Never the same as the bet price column.
DEFAULT_REFERENCE_COL = "pinnacle"
# Players with few recorded matches sit at/near the default 1500 Elo, so any
# "edge" the model shows against the market for them is model ignorance, not
# real signal -- skip until both players have a minimally informative sample.
MIN_MATCHES_PLAYED = 10
# Refuse to bet columns that aren't simultaneously purchasable prices.
NON_ATTAINABLE_PRICE_COLS = frozenset({"market_max"})


def _bet_price(row, side: str, bet_price_col: str) -> float:
    return getattr(row, f"player{side}_{bet_price_col}_odds")


def run_backtest(matches: pd.DataFrame, min_train_seasons: int = 5,
                  edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
                  kelly_fraction: float = staking.DEFAULT_KELLY_FRACTION,
                  starting_bankroll: float = 10_000.0,
                  bet_price_col: str = DEFAULT_BET_PRICE_COL,
                  reference_col: str = DEFAULT_REFERENCE_COL,
                  min_matches_played: int = MIN_MATCHES_PLAYED,
                  surface_speed_index: dict | None = None,
                  use_market: bool = True) -> tuple[pd.DataFrame, dict]:
    if bet_price_col in NON_ATTAINABLE_PRICE_COLS:
        raise ValueError(
            f"'{bet_price_col}' is a running maximum over the market's lifetime, not a "
            "price you could actually have bet. Backtesting against it fabricates "
            "profit. Use 'market_avg' or 'bet365'. See edge_audit.price_attainability_report."
        )
    if bet_price_col == reference_col:
        raise ValueError(
            f"bet_price_col and reference_col are both '{reference_col}'. The model is "
            "trained with the reference price as a feature, so this would compare a book "
            "against itself and produce meaningless edges."
        )

    table, _ = build_feature_table(matches, surface_speed_index=surface_speed_index)
    table = attach_market_probability(table, odds_col=reference_col)
    table = table.dropna(subset=[f"player1_{reference_col}_odds",
                                  f"player2_{reference_col}_odds"])
    table = table[(table["player1_matches_played"] >= min_matches_played) &
                  (table["player2_matches_played"] >= min_matches_played)]
    table["season"] = table["date"].dt.year
    seasons = sorted(table["season"].unique())

    bankroll = starting_bankroll
    bets = []

    for i, season in enumerate(seasons):
        if i < min_train_seasons:
            continue
        train_df = table[table["season"] < season]
        test_df = table[table["season"] == season].sort_values("date")
        if train_df.empty or test_df.empty:
            continue
        model = model_mod.train(train_df, use_market=use_market)
        p1_probs = model_mod.predict_proba(model, test_df)

        for row, p1_prob in zip(test_df.itertuples(index=False), p1_probs):
            if bankroll <= 0 or np.isnan(p1_prob):
                continue
            ref1 = row.market_prob_p1
            if pd.isna(ref1):
                continue
            ref2 = 1.0 - ref1
            edge1 = odds_math.edge(p1_prob, ref1)
            edge2 = odds_math.edge(1 - p1_prob, ref2)

            if edge1 > edge_threshold:
                side, model_p, ref_p, edge_val = "1", p1_prob, ref1, edge1
            elif edge2 > edge_threshold:
                side, model_p, ref_p, edge_val = "2", 1 - p1_prob, ref2, edge2
            else:
                continue

            price = _bet_price(row, side, bet_price_col)
            if pd.isna(price) or price <= 1.0:
                continue

            stake = staking.stake_size(bankroll, model_p, price, kelly_fraction)
            if stake <= 0:
                continue

            player_won = (row.label == 1) if side == "1" else (row.label == 0)
            pnl = stake * (price - 1.0) if player_won else -stake
            bankroll += pnl

            bets.append({
                "date": row.date, "tour": row.tour, "season": season,
                "surface": row.surface, "tier": getattr(row, "tier", None),
                "player": row.player1 if side == "1" else row.player2,
                "opponent": row.player2 if side == "1" else row.player1,
                "model_prob": model_p, "reference_prob": ref_p, "edge": edge_val,
                "price": price, "stake": stake, "won": player_won, "pnl": pnl,
                "bankroll_after": bankroll,
            })

    bets_df = pd.DataFrame(bets)
    summary = _summarize(bets_df, starting_bankroll, bet_price_col, reference_col)
    return bets_df, summary


def _summarize(bets_df: pd.DataFrame, starting_bankroll: float,
                bet_price_col: str, reference_col: str) -> dict:
    base = {"bet_at": bet_price_col, "priced_against": reference_col}
    if bets_df.empty:
        return {**base, "n_bets": 0,
                "message": "No qualifying value bets found in this period."}

    total_staked = float(bets_df["stake"].sum())
    total_pnl = float(bets_df["pnl"].sum())
    # Flat-stake significance: the Kelly-weighted P&L above answers "what would
    # my bankroll have done", this answers "is the edge real at all".
    sig = edge_audit.roi_with_significance(
        bets_df["won"].to_numpy(), bets_df["price"].to_numpy())

    return {
        **base,
        "n_bets": len(bets_df),
        "win_rate": round(float(bets_df["won"].mean()), 4),
        "total_staked": round(total_staked, 2),
        "total_pnl": round(total_pnl, 2),
        "roi_on_turnover": round(total_pnl / total_staked, 4) if total_staked else 0.0,
        "starting_bankroll": starting_bankroll,
        "final_bankroll": round(starting_bankroll + total_pnl, 2),
        "mean_edge_vs_reference": round(float(bets_df["edge"].mean()), 4),
        "seasons": sorted(bets_df["season"].unique().tolist()),
        # The numbers that decide whether any of the above means anything.
        "flat_stake_roi": sig["roi"],
        "flat_stake_t_stat": sig["t_stat"],
        "statistically_significant": sig["significant"],
        "verdict": sig["interpretation"],
    }
