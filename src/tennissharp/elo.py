"""Overall + surface-specific Elo ratings, computed chronologically.

Surface Elo is the single strongest predictor in most published tennis
betting models, well ahead of the raw ATP/WTA ranking. We maintain one
"overall" rating per player plus one rating per surface, using the
FiveThirtyEight-style dynamic K-factor (new players move faster than
established ones) scaled by tournament importance.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

DEFAULT_RATING = 1500.0
SURFACES = ("Hard", "Clay", "Grass", "Carpet")


def normalize_surface(raw) -> str | None:
    """Map a surface string onto one of SURFACES, or None if it names none.

    Worth a function because the failure is silent in both directions:
    `EloRatings.get` returns the 1500 default for anything outside SURFACES
    while `update` folds the same string into "Hard", so an unrecognised
    value never raises -- it just sets both players to the default and makes
    elo_surface_diff exactly zero. TennisExplorer writes "-" for an event
    with no surface listed, and "-" is truthy, so it passes any `or` fallback
    untouched.
    """
    if raw is None:
        return None
    text = str(raw).strip().lower()
    for surface in SURFACES:
        if surface.lower() in text:
            return surface
    return None

# Multiplies the base K-factor by tournament importance. Unrecognized/older
# tier labels fall back to 1.0 via TIER_WEIGHTS.get(tier, 1.0).
TIER_WEIGHTS = {
    "Grand Slam": 1.15,
    "Masters 1000": 1.05,
    "Masters Cup": 1.10,
    "Premier Mandatory": 1.10,
    "Premier 5": 1.05,
    "ATP500": 1.0,
    "Premier": 1.0,
    "ATP250": 0.9,
    "International": 0.9,
    "International Gold": 0.95,
}


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def k_factor(matches_played: int, tier: str | None, base: float = 250.0, offset: float = 5.0,
             power: float = 0.4) -> float:
    dynamic = base / (matches_played + offset) ** power
    return dynamic * TIER_WEIGHTS.get(tier or "", 1.0)


@dataclass
class _PlayerState:
    overall: float = DEFAULT_RATING
    surface: dict = field(default_factory=lambda: {s: DEFAULT_RATING for s in SURFACES})
    matches_played: int = 0
    surface_matches_played: dict = field(default_factory=lambda: {s: 0 for s in SURFACES})


class EloRatings:
    """Tracks overall + per-surface Elo for every player seen so far."""

    def __init__(self) -> None:
        self._players: dict[str, _PlayerState] = {}

    def _state(self, player: str) -> _PlayerState:
        return self._players.setdefault(player, _PlayerState())

    def get(self, player: str, surface: str | None = None) -> tuple[float, float]:
        """Return (overall_rating, surface_rating) for a player, pre-match."""
        state = self._state(player)
        surf_rating = state.surface.get(surface, DEFAULT_RATING) if surface in SURFACES else DEFAULT_RATING
        return state.overall, surf_rating

    def matches_played(self, player: str) -> int:
        return self._state(player).matches_played

    def update(self, winner: str, loser: str, surface: str, tier: str | None) -> None:
        w, l = self._state(winner), self._state(loser)
        surface = surface if surface in SURFACES else "Hard"

        k_w = k_factor(w.matches_played, tier)
        k_l = k_factor(l.matches_played, tier)
        exp_w = expected_score(w.overall, l.overall)
        w.overall += k_w * (1 - exp_w)
        l.overall += k_l * (0 - (1 - exp_w))
        w.matches_played += 1
        l.matches_played += 1

        k_w_s = k_factor(w.surface_matches_played[surface], tier)
        k_l_s = k_factor(l.surface_matches_played[surface], tier)
        exp_w_s = expected_score(w.surface[surface], l.surface[surface])
        w.surface[surface] += k_w_s * (1 - exp_w_s)
        l.surface[surface] += k_l_s * (0 - (1 - exp_w_s))
        w.surface_matches_played[surface] += 1
        l.surface_matches_played[surface] += 1

    def snapshot(self) -> pd.DataFrame:
        """Current ratings table, one row per player, for reporting/live use."""
        rows = []
        for player, state in self._players.items():
            row = {
                "player": player,
                "elo_overall": round(state.overall, 1),
                "matches_played": state.matches_played,
            }
            for s in SURFACES:
                row[f"elo_{s.lower()}"] = round(state.surface[s], 1)
                row[f"matches_{s.lower()}"] = state.surface_matches_played[s]
            rows.append(row)
        return pd.DataFrame(rows).sort_values("elo_overall", ascending=False).reset_index(drop=True)


def compute_pre_match_ratings(matches: pd.DataFrame) -> pd.DataFrame:
    """Walk matches chronologically, recording each player's rating *before*
    that match (to avoid leakage), then applying the result.

    `matches` must be sorted ascending by date and have columns:
    winner, loser, surface, tier.
    """
    elo = EloRatings()
    records = []
    for row in matches.itertuples(index=False):
        w_overall, w_surf = elo.get(row.winner, row.surface)
        l_overall, l_surf = elo.get(row.loser, row.surface)
        records.append({
            "winner_elo_overall": w_overall,
            "winner_elo_surface": w_surf,
            "loser_elo_overall": l_overall,
            "loser_elo_surface": l_surf,
        })
        elo.update(row.winner, row.loser, row.surface, getattr(row, "tier", None))
    ratings = pd.DataFrame(records, index=matches.index)
    return pd.concat([matches, ratings], axis=1), elo
