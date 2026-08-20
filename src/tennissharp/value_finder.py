"""Combine the trained model + persisted player state with live odds to find
value bets: matches where our estimated win probability clears the
de-vigged market probability by more than a threshold.
"""
from __future__ import annotations

import difflib
import unicodedata

import numpy as np
import pandas as pd

from tennissharp import model as model_mod
from tennissharp import odds_math, staking
from tennissharp.elo import expected_score
from tennissharp.features import MARKET_FEATURE, LiveState
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
                           best_of: int, surface_speed: float = 1.0,
                           as_of=None) -> dict:
    a_overall, a_surf = state.elo.get(player_a, surface)
    b_overall, b_surf = state.elo.get(player_b, surface)
    a_pts = state.last_rank_pts.get(player_a)
    b_pts = state.last_rank_pts.get(player_b)
    rank_pts_diff = 0.0
    if a_pts and b_pts:
        rank_pts_diff = np.log1p(a_pts) - np.log1p(b_pts)
    a_h2h, b_h2h = state.h2h_wins(player_a, player_b)

    as_of = as_of if as_of is not None else pd.Timestamp.now().normalize()
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
        "days_rest_diff": state.days_rest(player_a, as_of) - state.days_rest(player_b, as_of),
        "matches_recent_diff": (state.matches_recent(player_a, as_of)
                                 - state.matches_recent(player_b, as_of)),
        "surface_switch_diff": (state.surface_switch(player_a, surface)
                                 - state.surface_switch(player_b, surface)),
    }


def _reference_market_probability(event: dict, home: str, away: str,
                                   exclude_bookmaker: str | None) -> float | None:
    """De-vigged consensus probability for `home`, built from every bookmaker
    in the event *except* the one we're about to price against.

    Excluding it matters: the model is trained with the market price as a
    feature, so scoring a bet at book X using X's own price as input compares
    X against itself and manufactures an edge of ~zero-but-noisy. Pricing
    against the consensus of the *other* books is the honest comparison, and
    is what a sharp bettor actually does (Pinnacle as reference, bet elsewhere).
    """
    probs = []
    for bookmaker in event.get("bookmakers", []):
        if exclude_bookmaker and bookmaker.get("title") == exclude_bookmaker:
            continue
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            if home in outcomes and away in outcomes:
                fair = odds_math.shin_devig([outcomes[home], outcomes[away]])
                probs.append(fair[0])
    if not probs:
        return None
    return float(np.median(probs))


def elo_only_probability(state: LiveState, player_a: str, player_b: str, surface: str) -> float:
    """Fallback estimate (pure surface-Elo expected score) for players the
    trained model can't be fed full features for, or as a sanity cross-check.
    """
    _, a_surf = state.elo.get(player_a, surface)
    _, b_surf = state.elo.get(player_b, surface)
    return expected_score(a_surf, b_surf)


def find_value_bets(state: LiveState, model, live_events: list[dict],
                     edge_threshold: float = 0.10,
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

        ta_a, ta_b = _ta_elo_for(ta_lookup, home), _ta_elo_for(ta_lookup, away)
        ta_elo_diff_a = (ta_a["elo"] - ta_b["elo"]) if ta_a and ta_b else None

        uses_market = getattr(model, "tennissharp_uses_market_", False)

        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                if home not in outcomes or away not in outcomes:
                    continue
                odds_a, odds_b = outcomes[home], outcomes[away]

                # Score the model against the OTHER books' consensus, never
                # against the book we're about to bet at (see
                # _reference_market_probability for why).
                row_feats = dict(feats)
                if uses_market:
                    ref = _reference_market_probability(
                        event, home, away, exclude_bookmaker=bookmaker.get("title"))
                    if ref is None:
                        continue  # only one book quoting: nothing to compare against
                    ref = min(max(ref, 1e-6), 1 - 1e-6)
                    row_feats[MARKET_FEATURE] = float(np.log(ref / (1 - ref)))

                cols = model_mod.feature_columns(uses_market)
                X = pd.DataFrame([{c: row_feats[c] for c in cols}])
                model_prob_a = float(model.predict_proba(X)[:, 1][0])

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
