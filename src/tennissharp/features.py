"""Turn chronological match results into a symmetric, leakage-free feature table.

Every match is stored in the source data as winner/loser, which a classifier
would trivially "solve" by always predicting the first column. We instead
assign each match's two players to a randomized (player1, player2) slot and
predict P(player1 wins), using only information known *before* the match
(pre-match Elo, recent form, head-to-head) as features.
"""
from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from tennissharp.elo import EloRatings
from tennissharp.tourney_matching import lookup_surface_speed

FORM_WINDOW = 10
FEATURE_COLUMNS = [
    "elo_overall_diff", "elo_surface_diff", "rank_points_diff",
    "form_diff", "h2h_diff", "best_of", "tourney_surface_speed",
]


@dataclass
class LiveState:
    """Everything needed to score a *future* matchup with the same features
    the model was trained on: Elo ratings, recent-form history, head-to-head
    record, and each player's last known ranking points. Persisted after a
    data update so scripts/find_value_bets.py doesn't need to replay all of
    match history to score today's matches.
    """
    elo: EloRatings
    form: dict = field(default_factory=dict)
    h2h: dict = field(default_factory=dict)
    last_rank_pts: dict = field(default_factory=dict)
    last_seen: dict = field(default_factory=dict)  # player -> last match date

    def form_rate(self, player: str) -> float:
        hist = self.form.get(player)
        return sum(hist) / len(hist) if hist else 0.5

    def h2h_wins(self, player: str, opponent: str) -> tuple[int, int]:
        key = _h2h_key(player, opponent)
        record = self.h2h.get(key, [0, 0])
        return (record[0], record[1]) if key[0] == player else (record[1], record[0])


def _stable_coin_flip(match_id: str) -> bool:
    """Deterministic pseudo-random player1/player2 assignment per match."""
    digest = hashlib.sha256(match_id.encode()).hexdigest()
    return int(digest[:8], 16) % 2 == 0


def _h2h_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def build_feature_table(matches: pd.DataFrame, form_window: int = FORM_WINDOW,
                         surface_speed_index: dict | None = None) -> pd.DataFrame:
    """`matches` must be sorted ascending by date with the columns produced by
    `tennissharp.data.odds_history.normalize` (winner, loser, surface, tier,
    winner_rank/loser_rank, winner_pts/loser_pts, odds, match_id, ...).

    `surface_speed_index` -- from `tourney_matching.build_surface_speed_index`
    -- is optional; a per-tournament-edition rating dated to when that edition
    was actually played (unlike Tennis Abstract's Elo, which is a live
    snapshot and would leak future information if joined onto historical
    matches). Omit it to fall back to a neutral 1.0 (average speed) for every
    match.
    """
    elo = EloRatings()
    form: dict[str, deque] = {}
    h2h: dict[tuple[str, str], list[int]] = {}
    last_rank_pts: dict[str, float] = {}
    last_seen: dict[str, object] = {}
    rows = []

    for row in matches.itertuples(index=False):
        winner, loser = row.winner, row.loser
        w_elo_overall, w_elo_surf = elo.get(winner, row.surface)
        l_elo_overall, l_elo_surf = elo.get(loser, row.surface)

        w_form_hist = form.setdefault(winner, deque(maxlen=form_window))
        l_form_hist = form.setdefault(loser, deque(maxlen=form_window))
        w_form = sum(w_form_hist) / len(w_form_hist) if w_form_hist else 0.5
        l_form = sum(l_form_hist) / len(l_form_hist) if l_form_hist else 0.5

        key = _h2h_key(winner, loser)
        record = h2h.setdefault(key, [0, 0])
        w_h2h_wins = record[0] if key[0] == winner else record[1]
        l_h2h_wins = record[1] if key[0] == winner else record[0]

        w_pts = np.log1p(row.winner_pts) if pd.notna(row.winner_pts) else np.nan
        l_pts = np.log1p(row.loser_pts) if pd.notna(row.loser_pts) else np.nan

        w_matches = elo.matches_played(winner)
        l_matches = elo.matches_played(loser)

        surface_speed = (
            lookup_surface_speed(surface_speed_index, row.date.year, row.tournament)
            if surface_speed_index is not None else 1.0
        )

        player1_is_winner = _stable_coin_flip(row.match_id)
        if player1_is_winner:
            p1, p2 = winner, loser
            p1_elo_o, p2_elo_o = w_elo_overall, l_elo_overall
            p1_elo_s, p2_elo_s = w_elo_surf, l_elo_surf
            p1_pts, p2_pts = w_pts, l_pts
            p1_form, p2_form = w_form, l_form
            p1_h2h, p2_h2h = w_h2h_wins, l_h2h_wins
            p1_odds = {k: getattr(row, f"{k}_w", np.nan) for k in ("pinnacle", "bet365", "market_max", "market_avg")}
            p2_odds = {k: getattr(row, f"{k}_l", np.nan) for k in ("pinnacle", "bet365", "market_max", "market_avg")}
            p1_matches, p2_matches = w_matches, l_matches
            label = 1
        else:
            p1, p2 = loser, winner
            p1_elo_o, p2_elo_o = l_elo_overall, w_elo_overall
            p1_elo_s, p2_elo_s = l_elo_surf, w_elo_surf
            p1_pts, p2_pts = l_pts, w_pts
            p1_form, p2_form = l_form, w_form
            p1_h2h, p2_h2h = l_h2h_wins, w_h2h_wins
            p1_odds = {k: getattr(row, f"{k}_l", np.nan) for k in ("pinnacle", "bet365", "market_max", "market_avg")}
            p2_odds = {k: getattr(row, f"{k}_w", np.nan) for k in ("pinnacle", "bet365", "market_max", "market_avg")}
            p1_matches, p2_matches = l_matches, w_matches
            label = 0

        rows.append({
            "match_id": row.match_id,
            "date": row.date,
            "tour": row.tour,
            "surface": row.surface,
            "tier": getattr(row, "tier", None),
            "best_of": row.best_of,
            "player1": p1,
            "player2": p2,
            "elo_overall_diff": p1_elo_o - p2_elo_o,
            "elo_surface_diff": p1_elo_s - p2_elo_s,
            "rank_points_diff": (p1_pts - p2_pts) if pd.notna(p1_pts) and pd.notna(p2_pts) else np.nan,
            "form_diff": p1_form - p2_form,
            "h2h_diff": p1_h2h - p2_h2h,
            "tourney_surface_speed": surface_speed,
            "player1_matches_played": p1_matches,
            "player2_matches_played": p2_matches,
            "player1_pinnacle_odds": p1_odds["pinnacle"],
            "player2_pinnacle_odds": p2_odds["pinnacle"],
            "player1_market_max_odds": p1_odds["market_max"],
            "player2_market_max_odds": p2_odds["market_max"],
            "player1_market_avg_odds": p1_odds["market_avg"],
            "player2_market_avg_odds": p2_odds["market_avg"],
            "label": label,
        })

        w_form_hist.append(1)
        l_form_hist.append(0)
        record[0 if key[0] == winner else 1] += 1
        if pd.notna(row.winner_pts):
            last_rank_pts[winner] = row.winner_pts
        if pd.notna(row.loser_pts):
            last_rank_pts[loser] = row.loser_pts
        last_seen[winner] = row.date
        last_seen[loser] = row.date
        elo.update(winner, loser, row.surface, getattr(row, "tier", None))

    table = pd.DataFrame(rows)
    table["rank_points_diff"] = table["rank_points_diff"].fillna(0.0)
    state = LiveState(elo=elo, form=form, h2h=h2h, last_rank_pts=last_rank_pts, last_seen=last_seen)
    return table, state
