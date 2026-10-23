"""Serve and return statistics per player, and a point-based match model.

Source: the TennisMyLife match database, which carries Jeff Sackmann's
schema -- the per-match statistics behind Tennis Abstract's player pages
(aces, double faults, serve points, first serves in and won, second serves
won, service games, break points saved and faced, for both players) for
the main tours, the challenger circuit and ATP qualifying. Tennis
Abstract's own per-player logs sit under paths its robots.txt disallows,
so the same numbers are taken from the mirror that publishes them.

Two uses:

1. A player's last-52-week profile, overall and on the match's surface:
   serve points won, return points won, ace and double-fault rates, first
   serve in / won, second serve won, hold and break rates, break points
   saved and converted, recent form and the head-to-head.
2. A forecast from those numbers alone. Barnett & Clarke (2005): the share
   of points A wins on serve against B is the tour average plus A's serve
   excess minus B's return excess, and the same for B; a game, tie-break,
   set and match are then the usual Markov chain over those two point
   probabilities. No market, no Elo -- a third, independent opinion.
"""
from __future__ import annotations

import functools
from collections import defaultdict

import pandas as pd

from tennissharp import market_compare as mc

WINDOW_DAYS = 365
MIN_SURFACE_MATCHES = 8     # below this the surface profile defers to overall
SHRINK_MATCHES = 10.0       # pseudo-matches pulling a thin profile to the average
SURFACES = ("Hard", "Clay", "Grass", "Carpet")


# ----------------------------------------------------------- data shaping ----

def long_format(matches: pd.DataFrame) -> pd.DataFrame:
    """One row per (match, player) with that player's serve counts and the
    opponent's, so return statistics fall out of the opponent's serve."""
    cols = ["ace", "df", "svpt", "1stin", "1stwon", "2ndwon", "svgms", "bpsaved", "bpfaced"]
    frames = []
    for me, opp, won in (("winner", "loser", 1), ("loser", "winner", 0)):
        f = pd.DataFrame({
            "date": matches["date"], "tournament": matches["tournament"],
            "surface": matches["surface"], "tier": matches["tier"],
            "tour": matches.get("source_tour"),
            "player": matches[me], "opponent": matches[opp], "won": won,
            "rank": matches.get(f"{me}_rank"),
        })
        for c in cols:
            f[c] = matches.get(f"{me}_{c}")
            f[f"opp_{c}"] = matches.get(f"{opp}_{c}")
        frames.append(f)
    out = pd.concat(frames, ignore_index=True)
    return out.dropna(subset=["player", "opponent"])


def _rate(num, den):
    return float(num) / float(den) if den and den > 0 else None


def profile(rows: pd.DataFrame) -> dict | None:
    """Aggregate serve/return numbers over the given rows of one player."""
    if rows.empty:
        return None
    s = rows[["ace", "df", "svpt", "1stin", "1stwon", "2ndwon", "svgms", "bpsaved", "bpfaced",
              "opp_ace", "opp_df", "opp_svpt", "opp_1stin", "opp_1stwon", "opp_2ndwon",
              "opp_svgms", "opp_bpsaved", "opp_bpfaced"]].sum(min_count=1)
    with_stats = int(rows["svpt"].notna().sum())
    svpt, opp_svpt = s["svpt"], s["opp_svpt"]
    return {
        "matches": int(len(rows)),
        "with_stats": with_stats,
        "wins": int(rows["won"].sum()),
        "losses": int(len(rows) - rows["won"].sum()),
        "spw": _rate(s["1stwon"] + s["2ndwon"], svpt),
        "rpw": _rate(opp_svpt - s["opp_1stwon"] - s["opp_2ndwon"], opp_svpt),
        "ace_pct": _rate(s["ace"], svpt),
        "df_pct": _rate(s["df"], svpt),
        "first_in": _rate(s["1stin"], svpt),
        "first_won": _rate(s["1stwon"], s["1stin"]),
        "second_won": _rate(s["2ndwon"], svpt - s["1stin"]),
        "hold_pct": (1.0 - _rate(s["bpfaced"] - s["bpsaved"], s["svgms"])
                     if _rate(s["bpfaced"] - s["bpsaved"], s["svgms"]) is not None else None),
        "break_pct": _rate(s["opp_bpfaced"] - s["opp_bpsaved"], s["opp_svgms"]),
        "bp_saved": _rate(s["bpsaved"], s["bpfaced"]),
        "bp_converted": _rate(s["opp_bpfaced"] - s["opp_bpsaved"], s["opp_bpfaced"]),
        "vs_ace_pct": _rate(s["opp_ace"], opp_svpt),
        "last_date": rows["date"].max().date().isoformat(),
    }


class StatBook:
    """Last-52-week profiles for every player in the window."""

    def __init__(self, matches: pd.DataFrame, as_of=None, window_days: int = WINDOW_DAYS):
        as_of = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
        since = as_of - pd.Timedelta(days=window_days)
        recent = matches[(matches["date"] >= since) & (matches["date"] <= as_of)]
        self.long = long_format(recent).sort_values("date")
        self.players = sorted(self.long["player"].unique())
        self._by_player = {p: g for p, g in self.long.groupby("player")}
        # Tour averages per circuit, the anchor of the point model.
        self.tour_avg = {}
        for tour, g in self.long.groupby("tour"):
            prof = profile(g)
            if prof and prof["spw"]:
                self.tour_avg[str(tour)] = prof["spw"]
        self.tour_avg.setdefault("all", profile(self.long)["spw"] if len(self.long) else 0.62)
        self._matches = recent

    def resolve(self, abbreviated: str) -> str | None:
        """The window's player denoted by a schedule-style name; on a tie
        (two players with the surname and initial) the busier one."""
        hits = [p for p in self.players if mc.name_matches(abbreviated, p)]
        if not hits:
            return None
        return max(hits, key=lambda p: len(self._by_player[p]))

    def stats(self, player: str, surface: str | None = None) -> dict | None:
        rows = self._by_player.get(player)
        if rows is None:
            return None
        overall = profile(rows)
        out = {"player": player, "overall": overall, "surface": None, "surface_name": surface}
        if surface:
            on = rows[rows["surface"].astype(str).str.lower() == str(surface).lower()]
            if len(on) >= MIN_SURFACE_MATCHES:
                out["surface"] = profile(on)
        last = rows.tail(10)
        out["form10"] = (int(last["won"].sum()), int(len(last) - last["won"].sum()))
        out["rank"] = (int(rows["rank"].dropna().iloc[-1])
                       if rows["rank"].notna().any() else None)
        return out

    def head_to_head(self, a: str, b: str) -> dict:
        rows = self.long[(self.long["player"] == a) & (self.long["opponent"] == b)]
        return {"wins_a": int(rows["won"].sum()), "wins_b": int(len(rows) - rows["won"].sum()),
                "last": rows["date"].max().date().isoformat() if len(rows) else None}

    def tour_average(self, tour: str | None) -> float:
        return self.tour_avg.get(str(tour), self.tour_avg["all"])


# ----------------------------------------------------------- point model ----

def blended_rates(st: dict, tour_avg: float, shrink: float = SHRINK_MATCHES) -> tuple[float, float]:
    """(serve points won, return points won) for the match: the surface
    profile where it exists, else overall, each shrunk toward the tour
    average by the number of matches behind it."""
    prof = st.get("surface") or st.get("overall") or {}
    n = prof.get("with_stats") or 0
    w = n / (n + shrink) if n else 0.0
    spw = prof.get("spw") if prof.get("spw") is not None else tour_avg
    rpw = prof.get("rpw") if prof.get("rpw") is not None else 1.0 - tour_avg
    return (w * spw + (1 - w) * tour_avg, w * rpw + (1 - w) * (1.0 - tour_avg))


def point_probabilities(serve_a, return_a, serve_b, return_b, tour_avg) -> tuple[float, float]:
    """Barnett & Clarke: p_a = f_av + (f_a - f_av) - (g_b - g_av), g_av = 1 - f_av."""
    g_av = 1.0 - tour_avg
    p_a = tour_avg + (serve_a - tour_avg) - (return_b - g_av)
    p_b = tour_avg + (serve_b - tour_avg) - (return_a - g_av)
    clip = lambda x: min(0.95, max(0.05, x))
    return clip(p_a), clip(p_b)


@functools.lru_cache(maxsize=None)
def game_probability(p: float) -> float:
    """Server with point probability p holds the game."""
    q = 1.0 - p
    return (p ** 4 * (1 + 4 * q + 10 * q ** 2)
            + 20 * p ** 5 * q ** 3 / (1.0 - 2 * p * q))


@functools.lru_cache(maxsize=None)
def tiebreak_probability(p: float, q: float) -> float:
    """A wins a tie-break; p = A's point probability on own serve, q = B's.
    A serves the first point, then two points each."""
    def server_is_a(k: int) -> bool:
        return k == 0 or ((k - 1) // 2) % 2 == 1

    @functools.lru_cache(maxsize=None)
    def win(a: int, b: int) -> float:
        if a >= 7 and a - b >= 2:
            return 1.0
        if b >= 7 and b - a >= 2:
            return 0.0
        if a >= 6 and b >= 6:
            both = p * (1 - q)
            lose = (1 - p) * q
            return both / (both + lose)
        pa = p if server_is_a(a + b) else 1.0 - q
        return pa * win(a + 1, b) + (1 - pa) * win(a, b + 1)

    return win(0, 0)


@functools.lru_cache(maxsize=None)
def set_probability(p: float, q: float, a_serves_first: bool = True) -> float:
    ga, gb = game_probability(p), game_probability(q)

    @functools.lru_cache(maxsize=None)
    def win(a: int, b: int) -> float:
        if a >= 6 and a - b >= 2:
            return 1.0
        if b >= 6 and b - a >= 2:
            return 0.0
        if a == 6 and b == 6:
            return tiebreak_probability(p, q)
        a_serving = ((a + b) % 2 == 0) == a_serves_first
        hold = ga if a_serving else 1.0 - gb
        return hold * win(a + 1, b) + (1 - hold) * win(a, b + 1)

    return win(0, 0)


def match_probability(p: float, q: float, best_of: int = 3) -> float:
    """A wins the match from the two point probabilities."""
    s = 0.5 * (set_probability(p, q, True) + set_probability(p, q, False))
    if best_of == 5:
        return s ** 3 * (10 - 15 * s + 6 * s * s)
    return s * s * (3 - 2 * s)


def stat_forecast(stats_a: dict | None, stats_b: dict | None, tour_avg: float,
                  best_of: int = 3) -> float | None:
    if not stats_a or not stats_b:
        return None
    sa, ra = blended_rates(stats_a, tour_avg)
    sb, rb = blended_rates(stats_b, tour_avg)
    p, q = point_probabilities(sa, ra, sb, rb, tour_avg)
    return match_probability(p, q, best_of)


# --------------------------------------------------------- leader tables ----

SERVE_LEADER_COLUMNS = ["player", "matches", "wins", "losses", "match_win_pct", "spw", "ace_pct",
                        "df_pct", "first_in_pct", "first_win_pct", "second_win_pct", "hold_pct"]
RETURN_LEADER_COLUMNS = ["player", "matches", "wins", "losses", "rpw", "vs_ace_pct", "break_pct",
                         "bp_converted"]


def leader_tables(book: StatBook, tour: str, pool: str, min_matches: int = 10) -> dict[str, pd.DataFrame]:
    """{surface -> serve table, 'return_'+surface -> return table} for one
    player pool, the shape the /leaders API endpoint serves. Pools: top50
    and 51-100 by the player's latest ranking in the window, challenger by
    where most of the matches were played."""
    longdf = book.long[book.long["tour"].astype(str).str.lower().str.startswith(tour.lower())] \
        if "tour" in book.long.columns else book.long
    latest_rank = longdf.dropna(subset=["rank"]).groupby("player")["rank"].last()
    chall_share = longdf.assign(c=longdf["tier"].astype(str).eq("C")).groupby("player")["c"].mean()
    if pool == "top50":
        players = latest_rank[latest_rank <= 50].index
    elif pool == "51-100":
        players = latest_rank[(latest_rank > 50) & (latest_rank <= 100)].index
    else:
        players = chall_share[chall_share > 0.5].index
    out = {}
    for surface in ("All",) + SURFACES:
        serve_rows, return_rows = [], []
        for p in players:
            rows = longdf[longdf["player"] == p]
            if surface != "All":
                rows = rows[rows["surface"].astype(str) == surface]
            if len(rows) < min_matches:
                continue
            prof = profile(rows)
            if not prof or prof["spw"] is None:
                continue
            serve_rows.append({"player": p, "matches": prof["matches"], "wins": prof["wins"],
                               "losses": prof["losses"],
                               "match_win_pct": prof["wins"] / prof["matches"], "spw": prof["spw"],
                               "ace_pct": prof["ace_pct"], "df_pct": prof["df_pct"],
                               "first_in_pct": prof["first_in"], "first_win_pct": prof["first_won"],
                               "second_win_pct": prof["second_won"], "hold_pct": prof["hold_pct"]})
            return_rows.append({"player": p, "matches": prof["matches"], "wins": prof["wins"],
                                "losses": prof["losses"], "rpw": prof["rpw"],
                                "vs_ace_pct": prof["vs_ace_pct"], "break_pct": prof["break_pct"],
                                "bp_converted": prof["bp_converted"]})
        serve = pd.DataFrame(serve_rows, columns=SERVE_LEADER_COLUMNS)
        ret = pd.DataFrame(return_rows, columns=RETURN_LEADER_COLUMNS)
        out[surface.lower()] = serve.sort_values("spw", ascending=False).reset_index(drop=True)
        out["return_" + surface.lower()] = ret.sort_values("rpw", ascending=False).reset_index(drop=True)
    return out
