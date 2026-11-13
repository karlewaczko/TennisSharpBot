"""Sharp-move alerts: one side of a match rising JUMP or more within half an
hour before the start at Polymarket or Kalshi, and the lowest bet365 price
still worth taking then.

Why (data/reports/profi_wetten_und_edge.md, section 4j): after such a jump,
bet365's NBA moneyline a minute later was worth +4 % on average against the
venue's close (median about nought, 75 moves in six days), +7 % where
bet365 had not moved yet. Spreads, totals, the NHL, football and tennis
showed nothing. bet365 follows within 0-3 minutes in the median, so the
alert has to be fast, and the whole thing is a test until the logged alerts
say otherwise.

Pure logic, no network: scripts/sharp_move_alert.py feeds it prices.
"""
from __future__ import annotations

import math
from collections import deque

JUMP = 0.03            # points of win chance (0.03 = 3 cents)
WINDOW_S = 1800        # within half an hour
COOLDOWN_S = 3 * 3600  # one alert per side and match in three hours
MARGIN = 0.02          # bet365 must pay this much more than the fair price


def min_odds(p: float, margin: float = MARGIN) -> float | None:
    """The lowest decimal odds worth taking on a side whose fair chance is
    `p`: the fair odds plus `margin`, rounded up to the cent."""
    if not 0 < p < 1:
        return None
    return math.ceil((1 + margin) / p * 100 - 1e-9) / 100


class Watch:
    """Half an hour of prices per venue and side; a price `jump` or more
    above the one half an hour earlier is a move, at most once per side of
    a match (across venues) in `cooldown_s`."""

    def __init__(self, jump: float = JUMP, window_s: float = WINDOW_S, cooldown_s: float = COOLDOWN_S):
        self.jump, self.window_s, self.cooldown_s = jump, window_s, cooldown_s
        self.hist: dict[str, deque] = {}
        self.fired: dict[str, float] = {}

    def seen(self, key: str) -> bool:
        return key in self.hist

    def update(self, key: str, side: str, t: float, p: float) -> dict | None:
        """Record venue-side `key`'s price `p` at `t` (seconds); a move of
        match side `side`, or None."""
        h = self.hist.setdefault(key, deque())
        if h and t <= h[-1][0]:
            return None
        h.append((t, p))
        while len(h) > 1 and h[1][0] <= t - self.window_s:   # keep the last price at or before half an hour ago
            h.popleft()
        if h[0][0] > t - self.window_s:                       # not half an hour of history yet
            return None
        before = h[0][1]
        if p - before >= self.jump - 1e-9 and t - self.fired.get(side, -math.inf) >= self.cooldown_s:
            self.fired[side] = t
            return {"key": key, "side": side, "t": t, "before": before, "now": p}
        return None


def fmt_pct(p: float) -> str:
    return f"{p * 100:.0f} %"


def fmt_odds(o: float | None) -> str:
    return "–" if o is None else f"{o:.2f}".replace(".", ",")


def alert_text(league: str, game: str, start_local: str, team: str, venue: str, before: float, now: float,
               others: dict[str, float], link: str | None = None) -> tuple[str, float, float | None]:
    """The message, the fair chance (the venues' prices for the side now, averaged) and the minimum odds."""
    prices = [now, *others.values()]
    fair = sum(prices) / len(prices)
    least = min_odds(fair)
    lines = [f"{league} · {game} · Start {start_local}",
             f"{venue}: {team} {fmt_pct(before)} → {fmt_pct(now)} in 30 Min."]
    lines += [f"{v} jetzt {fmt_pct(p)}" for v, p in others.items()]
    lines.append(f"bet365 lohnt ab Quote {fmt_odds(least)} (fair {fmt_odds(1 / fair)})")
    lines.append("Test: nur Siegerwette, sofort prüfen, bet365 zieht meist binnen 1–3 Minuten nach.")
    if link:
        lines.append(link)
    return "\n".join(lines), fair, least
