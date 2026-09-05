"""Fractional Kelly bankroll staking.

Full Kelly is provably growth-optimal *only* if your win-probability estimate
is exact -- any model error gets amplified into oversized bets and brutal
drawdowns. Professional bettors near-universally stake a fraction (commonly
10-25%) of full Kelly instead. We default to 25% ("quarter Kelly") and cap
any single stake as a safety backstop against feature bugs or bad odds data.
"""
from __future__ import annotations

DEFAULT_KELLY_FRACTION = 0.25
DEFAULT_MAX_STAKE_FRACTION = 0.05  # never risk more than 5% of bankroll on one bet


def full_kelly_fraction(model_probability: float, decimal_odds: float) -> float:
    """Fraction of bankroll suggested by full Kelly. Negative means no edge
    (don't bet); the caller should clip at 0.
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    p = model_probability
    q = 1.0 - p
    return (b * p - q) / b


def stake_size(bankroll: float, model_probability: float, decimal_odds: float,
                kelly_fraction: float = DEFAULT_KELLY_FRACTION,
                max_stake_fraction: float = DEFAULT_MAX_STAKE_FRACTION) -> float:
    """Bet size in the same currency units as `bankroll`. Returns 0 if the
    model sees no edge at these odds.
    """
    full = full_kelly_fraction(model_probability, decimal_odds)
    if full <= 0:
        return 0.0
    fraction = min(full * kelly_fraction, max_stake_fraction)
    return bankroll * fraction
