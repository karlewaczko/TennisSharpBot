"""Combine the trained model + persisted player state with live odds to find
value bets: matches where our estimated win probability clears the
de-vigged market probability by more than a threshold.
"""
from __future__ import annotations

import difflib
import unicodedata

import numpy as np
import pandas as pd

from tennissharp import odds_math, staking
from tennissharp.elo import expected_score
from tennissharp.features import FEATURE_COLUMNS, LiveState
from tennissharp.name_matching import build_name_index, match_full_name

DEFAULT_SURFACE = "Hard"


def _fold(name: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return stripped.strip().lower()


def _ta_elo_lookup(ta_elo: pd.DataFrame | None) -> dict[str, dict]:
    """`ta_elo` uses the same 'Firstname Lastname' style as live-odds feeds
    (both list players naturally), so no Lastname-F. style conversion is
    needed here -- just fuzzy-match on the plain name.
    """
    if ta_elo is None or ta_elo.empty:
        return {}
    return {_fold(row.player): row._asdict() for row in ta_elo.itertuples(index=False)}


def _ta_elo_for(lookup: dict[str, dict], full_name: str) -> dict | None:
    if not lookup:
        return None
    key = _fold(full_name)
    if key in lookup:
        return lookup[key]
    close = difflib.get_close_matches(key, lookup.keys(), n=1, cutoff=0.85)
    return lookup[close[0]] if close else None


def _features_for_matchup(state: LiveState, player_a: str, player_b: str, surface: str,
                           best_of: int, surface_speed: float = 1.0) -> dict:
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
        # The Odds API doesn't expose which specific tournament/venue a match
        # is at, so we can't look up a real per-tournament rating here -- 1.0
        # (average speed) matches the neutral default used wherever the
        # historical join in tourney_matching.py can't find a match either.
        "tourney_surface_speed": surface_speed,
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
                     bankroll: float = 10_000.0,
                     ta_elo: pd.DataFrame | None = None) -> pd.DataFrame:
    """`live_events` is the JSON list from
    `tennissharp.data.live_odds.fetch_all_active_tennis_odds()`.

    `ta_elo` (optional) is Tennis Abstract's current Elo snapshot -- from
    `tennissharp.data.tennisabstract.fetch_all_elo_ratings()`. It's attached
    as `ta_elo_diff`/`ta_helo_diff` cross-check columns for manual review,
    not fed into the trained model (which was never trained with it, since
    Tennis Abstract only publishes a live snapshot, not a re-creatable
    historical series -- see data/tennisabstract.py).
    """
    known_players = list(state.elo._players.keys())  # noqa: SLF001 - internal but read-only use
    name_index = build_name_index(known_players)
    ta_lookup = _ta_elo_lookup(ta_elo)
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

        ta_a, ta_b = _ta_elo_for(ta_lookup, home), _ta_elo_for(ta_lookup, away)
        ta_elo_diff_a = (ta_a["elo"] - ta_b["elo"]) if ta_a and ta_b else None

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
                    side_player, side_opp, model_p, fair_p, edge_val, price, ta_diff = (
                        player_a, player_b, model_prob_a, fair_a, edge_a, odds_a, ta_elo_diff_a)
                elif edge_b > edge_threshold:
                    ta_diff_b = -ta_elo_diff_a if ta_elo_diff_a is not None else None
                    side_player, side_opp, model_p, fair_p, edge_val, price, ta_diff = (
                        player_b, player_a, 1 - model_prob_a, fair_b, edge_b, odds_b, ta_diff_b)
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
                    "ta_elo_diff": round(ta_diff, 1) if ta_diff is not None else None,
                    "commence_time": event.get("commence_time"),
                })

    return pd.DataFrame(rows).sort_values("edge", ascending=False) if rows else pd.DataFrame(rows)
