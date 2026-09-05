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
FATIGUE_WINDOW_DAYS = 21
# `days_rest` saturates here. During training that always means a genuine
# layoff, because the player's previous match is by construction in the data.
# At serving time it can also mean our feed simply lost track of the player,
# which is a different thing entirely -- see LiveState.is_stale.
DAYS_REST_CAP = 60

# The base feature set: everything derivable from results alone.
FEATURE_COLUMNS = [
    "elo_overall_diff", "elo_surface_diff", "rank_points_diff",
    "form_diff", "h2h_diff", "best_of", "tourney_surface_speed",
    # Workload/rest context. Tennis is unusual in that a player's schedule is
    # public and highly variable (deep runs mean back-to-back matches), so
    # these are cheap to compute and plausibly not fully priced in.
    "days_rest_diff", "matches_recent_diff", "surface_switch_diff",
]

# Same, plus the de-vigged market price. `model.py` trains on this when a
# market probability is available -- see `train(..., use_market=True)`.
MARKET_FEATURE = "market_logit"
FEATURE_COLUMNS_WITH_MARKET = [MARKET_FEATURE] + FEATURE_COLUMNS


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
    recent_dates: dict = field(default_factory=dict)  # player -> deque of match dates
    last_surface: dict = field(default_factory=dict)  # player -> last surface played

    def form_rate(self, player: str) -> float:
        hist = self.form.get(player)
        return sum(hist) / len(hist) if hist else 0.5

    def h2h_wins(self, player: str, opponent: str) -> tuple[int, int]:
        key = _h2h_key(player, opponent)
        record = self.h2h.get(key, [0, 0])
        return (record[0], record[1]) if key[0] == player else (record[1], record[0])

    def days_rest(self, player: str, as_of, default: float = 14.0) -> float:
        last = self.last_seen.get(player)
        if last is None:
            return default
        return _days_rest(as_of, last, default)

    def is_stale(self, player: str, as_of) -> bool:
        """True when our record of this player has run out, so his rest,
        form and fatigue features describe a gap in the feed rather than the
        player.

        Nothing distinguishes the two at the level of the number itself: a
        genuine two-month layoff and a player whose matches we stopped
        receiving both saturate `days_rest`. During training the distinction
        cannot arise -- the previous match is always in the data -- so the
        model learned the saturated value as 'well rested' and applies that
        reading to a stale row.
        """
        last = self.last_seen.get(player)
        if last is None:
            return True
        return _days_rest(as_of, last) >= DAYS_REST_CAP

    def matches_recent(self, player: str, as_of, window_days: int = FATIGUE_WINDOW_DAYS) -> int:
        return _count_recent(self.recent_dates.get(player), as_of, window_days)

    def surface_switch(self, player: str, surface: str) -> int:
        prev = self.last_surface.get(player)
        return 0 if prev is None else int(prev != surface)


def _days_rest(as_of, last, default: float = 14.0) -> float:
    """Days between a player's previous match and this one, capped -- an
    8-month injury layoff and a 3-week break are both just 'well rested',
    and leaving the raw value uncapped lets rare comebacks dominate the split.
    """
    try:
        delta = (as_of - last).days
    except (TypeError, AttributeError):
        return default
    return float(min(max(delta, 0), DAYS_REST_CAP))


def _count_recent(dates, as_of, window_days: int) -> int:
    if not dates:
        return 0
    count = 0
    for d in dates:
        try:
            if 0 <= (as_of - d).days <= window_days:
                count += 1
        except (TypeError, AttributeError):
            continue
    return count


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
    recent_dates: dict[str, deque] = {}
    last_surface: dict[str, str] = {}
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

        # Workload/rest, all computed from matches strictly before this one.
        w_rest = _days_rest(row.date, last_seen.get(winner))
        l_rest = _days_rest(row.date, last_seen.get(loser))
        w_recent = _count_recent(recent_dates.get(winner), row.date, FATIGUE_WINDOW_DAYS)
        l_recent = _count_recent(recent_dates.get(loser), row.date, FATIGUE_WINDOW_DAYS)
        w_switch = int(last_surface.get(winner, row.surface) != row.surface)
        l_switch = int(last_surface.get(loser, row.surface) != row.surface)

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
            p1_rest, p2_rest = w_rest, l_rest
            p1_recent, p2_recent = w_recent, l_recent
            p1_switch, p2_switch = w_switch, l_switch
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
            p1_rest, p2_rest = l_rest, w_rest
            p1_recent, p2_recent = l_recent, w_recent
            p1_switch, p2_switch = l_switch, w_switch
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
            "days_rest_diff": p1_rest - p2_rest,
            "matches_recent_diff": p1_recent - p2_recent,
            "surface_switch_diff": p1_switch - p2_switch,
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
        for player in (winner, loser):
            recent_dates.setdefault(player, deque(maxlen=40)).append(row.date)
            last_surface[player] = row.surface
        elo.update(winner, loser, row.surface, getattr(row, "tier", None))

    table = pd.DataFrame(rows)
    table["rank_points_diff"] = table["rank_points_diff"].fillna(0.0)
    state = LiveState(elo=elo, form=form, h2h=h2h, last_rank_pts=last_rank_pts,
                       last_seen=last_seen, recent_dates=recent_dates,
                       last_surface=last_surface)
    return table, state


def attach_market_probability(table: pd.DataFrame, odds_col: str = "pinnacle") -> pd.DataFrame:
    """Add the de-vigged market probability (and its logit) for player1.

    Kept separate from `build_feature_table` because it's only meaningful for
    rows that actually have odds, and because the market price is the one
    "feature" that is emphatically *not* ours -- see the README on why the
    model is trained against it rather than pretending to beat it.
    """
    from tennissharp.odds_math import shin_devig

    p1_col, p2_col = f"player1_{odds_col}_odds", f"player2_{odds_col}_odds"
    out = table.copy()
    has_odds = out[p1_col].notna() & out[p2_col].notna()
    market_p1 = np.full(len(out), np.nan)
    pairs = out.loc[has_odds, [p1_col, p2_col]].to_numpy()
    if len(pairs):
        devigged = np.array([shin_devig([a, b]) for a, b in pairs])[:, 0]
        market_p1[has_odds.to_numpy()] = devigged
    out["market_prob_p1"] = market_p1
    clipped = np.clip(market_p1, 1e-6, 1 - 1e-6)
    out[MARKET_FEATURE] = np.log(clipped / (1 - clipped))
    return out
