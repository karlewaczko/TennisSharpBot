"""Combine the trained model + persisted player state with live odds to find
value bets: matches where our estimated win probability clears the
de-vigged market probability by more than a threshold.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tennissharp import odds_math, staking
from tennissharp.elo import expected_score
from tennissharp.features import FEATURE_COLUMNS, LiveState
from tennissharp.name_matching import build_name_index, match_full_name

DEFAULT_SURFACE = "Hard"


def _features_for_matchup(state: LiveState, player_a: str, player_b: str, surface: str,
                           best_of: int) -> dict:
    a_overall, a_surf = state.elo.get(player_a, surface)
    b_overall, b_surf = state.elo.get(player_b, surface)
    a_pts = state.last_rank_pts.get(player_a)
    b_pts = state.last_rank_pts.get(player_b)
    rank_pts_diff = 0.0
    if a_pts and b_pts:
        rank_pts_diff = np.log1p(a_pts) - np.log1p(b_pts)
    a_h2h, b_h2h = state.h2h_wins(player_a, player_b)
    return {
        "elo_overall_diff": a_overall - b_overall,
        "elo_surface_diff": a_surf - b_surf,
        "rank_points_diff": rank_pts_diff,
        "form_diff": state.form_rate(player_a) - state.form_rate(player_b),
        "h2h_diff": a_h2h - b_h2h,
        "best_of": best_of,
    }


def elo_only_probability(state: LiveState, player_a: str, player_b: str, surface: str) -> float:
    """Fallback estimate (pure surface-Elo expected score) for players the
    trained model can't be fed full features for, or as a sanity cross-check.
    """
    _, a_surf = state.elo.get(player_a, surface)
    _, b_surf = state.elo.get(player_b, surface)
    return expected_score(a_surf, b_surf)


def find_value_bets(state: LiveState, model, live_events: list[dict],
                     edge_threshold: float = 0.03,
                     kelly_fraction: float = staking.DEFAULT_KELLY_FRACTION,
                     bankroll: float = 10_000.0) -> pd.DataFrame:
    """`live_events` is the JSON list from
    `tennissharp.data.live_odds.fetch_all_active_tennis_odds()`.
    """
    known_players = list(state.elo._players.keys())  # noqa: SLF001 - internal but read-only use
    name_index = build_name_index(known_players)
    rows = []

    for event in live_events:
        home, away = event.get("home_team"), event.get("away_team")
        if not home or not away:
            continue
        player_a = match_full_name(home, known_players, name_index)
        player_b = match_full_name(away, known_players, name_index)
        if not player_a or not player_b:
            continue

        surface = DEFAULT_SURFACE  # The Odds API doesn't expose surface; override via CLI if known
        best_of = 3
        feats = _features_for_matchup(state, player_a, player_b, surface, best_of)
        X = pd.DataFrame([{c: feats[c] for c in FEATURE_COLUMNS}])
        model_prob_a = float(model.predict_proba(X)[:, 1][0])

        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                if home not in outcomes or away not in outcomes:
                    continue
                odds_a, odds_b = outcomes[home], outcomes[away]
                fair_a, fair_b = odds_math.shin_devig([odds_a, odds_b])
                edge_a = odds_math.edge(model_prob_a, fair_a)
                edge_b = odds_math.edge(1 - model_prob_a, fair_b)

                if edge_a > edge_threshold:
                    side_player, side_opp, model_p, fair_p, edge_val, price = (
                        player_a, player_b, model_prob_a, fair_a, edge_a, odds_a)
                elif edge_b > edge_threshold:
                    side_player, side_opp, model_p, fair_p, edge_val, price = (
                        player_b, player_a, 1 - model_prob_a, fair_b, edge_b, odds_b)
                else:
                    continue

                rows.append({
                    "bookmaker": bookmaker.get("title"),
                    "player": side_player,
                    "opponent": side_opp,
                    "model_prob": round(model_p, 4),
                    "market_fair_prob": round(fair_p, 4),
                    "edge": round(edge_val, 4),
                    "odds": price,
                    "suggested_stake": round(staking.stake_size(bankroll, model_p, price, kelly_fraction), 2),
                    "commence_time": event.get("commence_time"),
                })

    return pd.DataFrame(rows).sort_values("edge", ascending=False) if rows else pd.DataFrame(rows)
