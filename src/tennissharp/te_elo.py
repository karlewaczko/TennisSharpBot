"""An Elo for every player TennisExplorer lists: ATP, WTA, Challenger, ITF
and UTR, from its daily result pages.

Tennis Abstract rates about 550 men and 500 women, so most of a day's
card (ITF and UTR, often two thirds of it) had no market-free opinion at
all. TennisExplorer's result page for a day lists every singles match
played, with the players' page slugs, so one pool of ratings over two
years of those pages covers nearly everyone. Players are keyed by slug,
not name, which keeps namesakes apart.

The rating is FiveThirtyEight's (src/tennissharp/elo.py's k_factor:
newcomers move fast, established players slowly), overall only: the day
page names no surface. A player's first rating depends on the level he or
she first appears at: a debutant at a UTR event is not as strong as one in
an ATP draw. `level_start` learns those starting points from a first pass.

Pure logic, no network: scripts/update_te_elo.py feeds it result rows.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .elo import expected_score, k_factor

LEVELS = ("ATP", "WTA", "Challenger", "ITF", "UTR", "Liga")
DEFAULT = 1500.0
MIN_SURE = 15          # matches each player needs before a forecast counts as settled
COLUMNS = ["slug", "name", "elo", "matches", "level", "first_date", "last_date"]


def level_of(tournament: str, url: str = "") -> str:
    """The same five-way split the dashboard shows (build_dashboard.category_of)."""
    name = str(tournament).lower()
    if "utr" in name:
        return "UTR"
    if "itf" in name or "futures" in name:
        return "ITF"
    if "challenger" in name:
        return "Challenger"
    if "nationalliga" in name or "league" in name or "liga" in name:
        return "Liga"
    return "WTA" if "-women/" in str(url) else "ATP"


def results(day: pd.DataFrame) -> pd.DataFrame:
    """The finished singles of one result page, winner first, in playing
    order: no doubles, no walkovers (no games played), no unfinished rows."""
    cols = ["date", "time", "tournament", "level", "winner", "winner_name", "loser", "loser_name",
            "odds_w", "odds_l", "match_id"]
    if day is None or day.empty:
        return pd.DataFrame(columns=cols)
    d = day.copy()
    d = d[d["player1_slug"].notna() & d["player2_slug"].notna()]
    d = d[~d["player1"].astype(str).str.contains("/") & ~d["player2"].astype(str).str.contains("/")]
    s1, s2 = pd.to_numeric(d["sets_won1"], errors="coerce"), pd.to_numeric(d["sets_won2"], errors="coerce")
    d = d[s1.notna() & s2.notna() & (s1 != s2) & d["score"].notna()]
    if d.empty:
        return pd.DataFrame(columns=cols)
    first = (pd.to_numeric(d["sets_won1"]) > pd.to_numeric(d["sets_won2"]))
    pick = lambda a, b: d[a].where(first, d[b])  # noqa: E731
    out = pd.DataFrame({
        "date": d["date"], "time": d["time"].fillna("99:99"), "tournament": d["tournament"],
        "level": [level_of(t, u) for t, u in zip(d["tournament"], d.get("tournament_url", ""))],
        "winner": pick("player1_slug", "player2_slug"), "winner_name": pick("player1", "player2"),
        "loser": pick("player2_slug", "player1_slug"), "loser_name": pick("player2", "player1"),
        "odds_w": pick("odds1", "odds2"), "odds_l": pick("odds2", "odds1"), "match_id": d["match_id"]})
    return out.drop_duplicates("match_id").sort_values(["date", "time"], kind="stable").reset_index(drop=True)


@dataclass
class Player:
    name: str
    elo: float
    matches: int
    level: str
    first_date: str
    last_date: str


class Ratings:
    """One rating per player slug; `start` gives a newcomer's rating by the
    level of the first match he or she is seen in."""

    def __init__(self, start: dict[str, float] | None = None):
        self.start = dict(start or {})
        self.players: dict[str, Player] = {}

    def _get(self, slug: str, name: str, level: str, date: str) -> Player:
        p = self.players.get(slug)
        if p is None:
            p = self.players[slug] = Player(name, self.start.get(level, DEFAULT), 0, level, date, date)
        return p

    def prob(self, a: str, b: str) -> float | None:
        """Chance that `a` beats `b`; None when either is unknown."""
        pa, pb = self.players.get(a), self.players.get(b)
        if pa is None or pb is None:
            return None
        return expected_score(pa.elo, pb.elo)

    def update(self, r) -> float:
        """Play one result row; the winner's chance beforehand."""
        w = self._get(r.winner, str(r.winner_name), r.level, str(r.date))
        lo = self._get(r.loser, str(r.loser_name), r.level, str(r.date))
        e = expected_score(w.elo, lo.elo)
        kw, kl = k_factor(w.matches, None), k_factor(lo.matches, None)
        w.elo += kw * (1 - e)
        lo.elo -= kl * (1 - e)
        for p, name in ((w, r.winner_name), (lo, r.loser_name)):
            p.matches += 1
            p.last_date = str(r.date)
            p.name = str(name)
        return e

    def play(self, rows: pd.DataFrame, record: list | None = None) -> None:
        """Every row in order; with `record`, each match's forecast before it
        was played (for the backtest)."""
        for r in rows.itertuples(index=False):
            if record is not None:
                pw, pl = self.players.get(r.winner), self.players.get(r.loser)
                record.append({"date": r.date, "level": r.level, "odds_w": r.odds_w, "odds_l": r.odds_l,
                               "n_min": min(pw.matches if pw else 0, pl.matches if pl else 0)})
            e = self.update(r)
            if record is not None:
                record[-1]["p"] = e

    def table(self) -> pd.DataFrame:
        rows = [{"slug": s, "name": p.name, "elo": round(p.elo, 1), "matches": p.matches, "level": p.level,
                 "first_date": p.first_date, "last_date": p.last_date} for s, p in self.players.items()]
        return pd.DataFrame(rows, columns=COLUMNS).sort_values("slug").reset_index(drop=True)

    @classmethod
    def from_table(cls, df: pd.DataFrame, start: dict[str, float] | None = None) -> "Ratings":
        r = cls(start)
        for row in df.itertuples(index=False):
            r.players[row.slug] = Player(str(row.name), float(row.elo), int(row.matches), str(row.level),
                                         str(row.first_date), str(row.last_date))
        return r


def level_start(rows: pd.DataFrame, min_matches: int = 20) -> dict[str, float]:
    """A newcomer's rating per level: the median rating, after one pass over
    `rows` from 1500, of the established players (`min_matches`+) whose most
    frequent level it is."""
    r = Ratings()
    r.play(rows)
    seen: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for col in ("winner", "loser"):
        for slug, level in zip(rows[col], rows["level"]):
            seen[slug][level] += 1
    by_level: dict[str, list[float]] = defaultdict(list)
    for slug, counts in seen.items():
        p = r.players[slug]
        if p.matches >= min_matches:
            by_level[max(counts, key=counts.get)].append(p.elo)
    return {lv: round(float(pd.Series(v).median()), 1) for lv, v in by_level.items() if len(v) >= 20}


def score(record: list[dict]) -> dict:
    """Log loss, Brier score and hit rate of the forecasts in `record`
    against the results, beside the de-vigged TennisExplorer odds on the same
    matches where there are any."""
    df = pd.DataFrame(record)
    if df.empty:
        return {}
    eps = 1e-6
    out = {"n": int(len(df)),
           "log_loss": round(float(-(df["p"].clip(eps, 1 - eps)).map(math.log).mean()), 4),
           "brier": round(float(((1 - df["p"]) ** 2).mean()), 4),
           "hit_rate": round(float((df["p"] > 0.5).mean() + 0.5 * (df["p"] == 0.5).mean()), 4)}
    m = df[(df["odds_w"] > 1) & (df["odds_l"] > 1)].copy()
    if len(m):
        iw, il = 1 / m["odds_w"], 1 / m["odds_l"]
        m["q"] = iw / (iw + il)
        out["with_odds"] = {
            "n": int(len(m)),
            "elo_log_loss": round(float(-(m["p"].clip(eps, 1 - eps)).map(math.log).mean()), 4),
            "market_log_loss": round(float(-(m["q"].clip(eps, 1 - eps)).map(math.log).mean()), 4),
            "elo_brier": round(float(((1 - m["p"]) ** 2).mean()), 4),
            "market_brier": round(float(((1 - m["q"]) ** 2).mean()), 4),
            "elo_hit_rate": round(float((m["p"] > 0.5).mean()), 4),
            "market_hit_rate": round(float((m["q"] > 0.5).mean()), 4)}
    return out


SCALE_MIN_MATCHES = 40   # matches in our pool before a player helps fit the scale


def fit_scale(pairs: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Least squares `ta = a + b * ours` over players both pools rate, so a
    rating of ours can face one of Tennis Abstract's: (a, b), or None with
    fewer than 30 pairs. Pairs more than 300 points off the first fit (a
    namesake matched wrongly) are dropped and the line fitted again."""
    if len(pairs) < 30:
        return None
    df = pd.DataFrame(pairs, columns=["ours", "ta"])
    for _ in range(2):
        b, a = np.polyfit(df["ours"], df["ta"], 1)
        keep = (df["ta"] - (a + b * df["ours"])).abs() <= 300
        if keep.all() or keep.sum() < 30:
            break
        df = df[keep]
    return round(float(a), 2), round(float(b), 4)


def on_ta_scale(elo: float, scale: tuple[float, float]) -> float:
    return scale[0] + scale[1] * elo
