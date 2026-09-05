"""Convert bookmaker decimal odds into de-vigged "fair" probabilities, and
measure the edge between those and a model's own probability estimate.

Two devigging methods are provided:
- `multiplicative_devig`: simplest approach, just rescales raw implied
  probabilities so they sum to 1. Good enough as a quick benchmark.
- `shin_devig`: Shin's (1992/1993) method, which additionally corrects for
  the favorite-longshot bias by modelling a fraction `z` of insider-informed
  stake. This is the standard used in most published sharp-betting research
  and is what we use as the default "true market probability" benchmark.
"""
from __future__ import annotations

import math


def implied_probability(decimal_odds: float) -> float:
    return 1.0 / decimal_odds


def overround(odds: list[float]) -> float:
    """Bookmaker margin, e.g. 0.05 == 5% overround."""
    return sum(implied_probability(o) for o in odds) - 1.0


def multiplicative_devig(odds: list[float]) -> list[float]:
    raw = [implied_probability(o) for o in odds]
    total = sum(raw)
    return [p / total for p in raw]


def _shin_prob(z: float, pi_i: float, sum_pi: float) -> float:
    z = min(z, 0.999999)
    inner = z * z + 4 * (1 - z) * pi_i * pi_i / sum_pi
    return (math.sqrt(inner) - z) / (2 * (1 - z))


def shin_devig(odds: list[float], tol: float = 1e-10, max_iter: int = 200) -> list[float]:
    """Closed-form-per-z formulation of Shin's model, solved for z by
    bisection. Realistic bookmaker margins (a few percent) keep z well
    under 0.3, so we bisect on [0, 0.3].
    """
    raw = [implied_probability(o) for o in odds]
    sum_pi = sum(raw)
    if sum_pi <= 1.0:
        return raw  # no overround to remove

    def total_at(z: float) -> float:
        return sum(_shin_prob(z, p, sum_pi) for p in raw) - 1.0

    lo, hi = 0.0, 0.3
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        if total_at(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    z = (lo + hi) / 2
    return [_shin_prob(z, p, sum_pi) for p in raw]


def edge(model_probability: float, market_probability: float) -> float:
    """Positive edge means the model thinks the outcome is more likely than
    the (de-vigged) market does -- a candidate value bet."""
    return model_probability - market_probability


def expected_value(model_probability: float, decimal_odds: float) -> float:
    """EV per unit staked. > 0 means positive expected value at these odds."""
    return model_probability * decimal_odds - 1.0
