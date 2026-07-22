"""Walk-forward historical backtest: train on the past, bet on the next
season, roll forward. Reports ROI and an "edge vs Pinnacle" proxy for CLV.

Note on CLV: true closing-line value needs the odds you actually bet at
*and* the market's final closing price as two separate numbers. This
dataset has one odds snapshot per bookmaker per match, so we treat the
de-vigged Pinnacle price (the sharpest book, and our devig benchmark) as a
stand-in for the closing line. A positive mean edge here is a reasonable
proxy for positive CLV, but isn't literally CLV -- say so in any report.
"""
from __future__ import annotations

import pandas as pd

from tennissharp import model as model_mod
from tennissharp import odds_math, staking
from tennissharp.features import build_feature_table

DEFAULT_EDGE_THRESHOLD = 0.03
DEFAULT_BET_PRICE_COL = "market_avg"  # the price you could plausibly get by shopping lines
# Players with few recorded matches sit at/near the default 1500 Elo, so any
# "edge" the model shows against the market for them is model ignorance, not
# real signal -- skip until both players have a minimally informative sample.
MIN_MATCHES_PLAYED = 10


def _bet_price(row, side: str, bet_price_col: str) -> float:
    return getattr(row, f"player{side}_{bet_price_col}_odds")


def run_backtest(matches: pd.DataFrame, min_train_seasons: int = 5,
                  edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
                  kelly_fraction: float = staking.DEFAULT_KELLY_FRACTION,
                  starting_bankroll: float = 10_000.0,
                  bet_price_col: str = DEFAULT_BET_PRICE_COL,
                  min_matches_played: int = MIN_MATCHES_PLAYED) -> tuple[pd.DataFrame, dict]:
    table, _ = build_feature_table(matches)
    table = table.dropna(subset=["player1_pinnacle_odds", "player2_pinnacle_odds"])
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
        model = model_mod.train(train_df)
        p1_probs = model_mod.predict_proba(model, test_df)

        for row, p1_prob in zip(test_df.itertuples(index=False), p1_probs):
            if bankroll <= 0:
                break
            fair1, fair2 = odds_math.shin_devig([row.player1_pinnacle_odds, row.player2_pinnacle_odds])
            edge1 = odds_math.edge(p1_prob, fair1)
            edge2 = odds_math.edge(1 - p1_prob, fair2)

            if edge1 > edge_threshold:
                side, model_p, fair_p, edge_val = "1", p1_prob, fair1, edge1
            elif edge2 > edge_threshold:
                side, model_p, fair_p, edge_val = "2", 1 - p1_prob, fair2, edge2
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
                "player": row.player1 if side == "1" else row.player2,
                "opponent": row.player2 if side == "1" else row.player1,
                "model_prob": model_p, "market_fair_prob": fair_p, "edge": edge_val,
                "price": price, "stake": stake, "won": player_won, "pnl": pnl,
                "bankroll_after": bankroll,
            })

    bets_df = pd.DataFrame(bets)
    summary = _summarize(bets_df, starting_bankroll)
    return bets_df, summary


def _summarize(bets_df: pd.DataFrame, starting_bankroll: float) -> dict:
    if bets_df.empty:
        return {"n_bets": 0, "message": "No qualifying value bets found in this period."}
    total_staked = bets_df["stake"].sum()
    total_pnl = bets_df["pnl"].sum()
    return {
        "n_bets": len(bets_df),
        "win_rate": round(bets_df["won"].mean(), 4),
        "total_staked": round(total_staked, 2),
        "total_pnl": round(total_pnl, 2),
        "roi_on_turnover": round(total_pnl / total_staked, 4) if total_staked else 0.0,
        "starting_bankroll": starting_bankroll,
        "final_bankroll": round(starting_bankroll + total_pnl, 2),
        "mean_edge_vs_pinnacle": round(bets_df["edge"].mean(), 4),
        "seasons": sorted(bets_df["season"].unique().tolist()),
    }
