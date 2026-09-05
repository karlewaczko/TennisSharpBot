"""Pure logic for the automatic value-bet scan: which rows are worth
alerting about that we haven't already sent, and pruning stale entries.

Kept free of any Telegram/network imports so it's unit-testable without a
bot token or the job-queue machinery.
"""
from __future__ import annotations

import pandas as pd

BetKey = tuple[str, str, str, str]


def bet_key(player: str, opponent: str, bookmaker: str, commence_time: str) -> BetKey:
    return (str(player), str(opponent), str(bookmaker), str(commence_time))


def filter_new_bets(df: pd.DataFrame, seen: set[BetKey]) -> pd.DataFrame:
    """Rows from `df` (as returned by value_finder.find_value_bets) whose key
    isn't already in `seen`. Does not mutate `seen` -- call `mark_seen`
    afterwards once the alert has actually been sent.
    """
    if df.empty:
        return df
    keys = df.apply(lambda r: bet_key(r["player"], r["opponent"], r["bookmaker"],
                                       r["commence_time"]), axis=1)
    return df[~keys.isin(seen)]


def mark_seen(df: pd.DataFrame, seen: set[BetKey]) -> None:
    for row in df.itertuples(index=False):
        seen.add(bet_key(row.player, row.opponent, row.bookmaker, row.commence_time))


def prune_past(seen: set[BetKey], now: pd.Timestamp) -> set[BetKey]:
    """Drop entries whose commence_time has passed, so `seen` doesn't grow
    forever over a long-running bot process."""
    kept = set()
    for key in seen:
        commence_time = key[3]
        try:
            ts = pd.Timestamp(commence_time)
            if ts.tzinfo is not None:
                ts = ts.tz_convert(None)
            if ts >= now:
                kept.add(key)
        except (ValueError, TypeError):
            continue  # unparseable timestamp: drop it rather than keep it forever
    return kept
