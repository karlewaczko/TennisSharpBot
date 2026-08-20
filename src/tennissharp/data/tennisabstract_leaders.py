"""Tennis Abstract Stat Leaders (tennisabstract.com/cgi-bin/leaders.cgi) --
Serve and Return leaderboards, overall and per surface.

This page's tables are built client-side by JavaScript from a per-match data
array, not server-rendered HTML, so it can't be scraped with
`pandas.read_html` like the Elo/surface-speed reports in `tennisabstract.py`.
Instead we fetch the same raw JS array the page's own script uses
(`jsmatches/leadersource*.js` -- one file per tour/player-pool combination)
and reimplement the exact aggregation the page's own `makeMatchTable()` JS
function performs, verified line-for-line against tennisabstract.com's own
source (view-source on leaders.cgi):

- `MATCH_COLUMNS` is copied verbatim from `var matchhead = [...]` in the
  leaders.cgi page source, and cross-checked against a real row of
  `leadersource.js` field-by-field (date/tourn/surf/... all lined up).
- The formulas in `compute_serve_leaders`/`compute_return_leaders` are
  copied from the page's own `if (showstats == 'o') {...}` / `'w'` blocks
  (e.g. `spw = (fwon+swon)/pts`, `rpw = 1 - (ofwon+oswon)/opts`).
- The default filters replicated here (surface="All", last-52-weeks span)
  match `filteropts['surface'][1]` / `filteropts['span'][1]` -- the page's
  own pre-selected defaults on a fresh page load, including the exact
  (non-calendar) "last 52" arithmetic: `today_yyyymmdd - 10000`.

`var matchmx = [...]` in each source file is valid JSON (all-double-quoted
string arrays), so no bespoke JS parsing is needed -- just slice it out and
`json.loads` it.
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd
import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)"}

# One raw-match-data source file per (tour, player pool). WTA has no
# Challenger leaderboard on tennisabstract.com (the query param is accepted
# but silently ignored, falling back to Top 50) so it's omitted here.
LEADERS_SOURCE_URLS = {
    ("atp", "top50"): "https://www.tennisabstract.com/jsmatches/leadersource.js",
    ("atp", "51-100"): "https://www.tennisabstract.com/jsmatches/leadersource51.js",
    ("atp", "challenger"): "https://www.tennisabstract.com/jsmatches/leadersource_chall.js",
    ("wta", "top50"): "https://www.tennisabstract.com/jsmatches/leadersource_wta.js",
    ("wta", "51-100"): "https://www.tennisabstract.com/jsmatches/leadersource51_wta.js",
}
POOLS_BY_TOUR = {
    "atp": ["top50", "51-100", "challenger"],
    "wta": ["top50", "51-100"],
}
SURFACES = ["All", "Hard", "Clay", "Grass", "Carpet"]

# Verbatim copy of `var matchhead = [...]` from the leaders.cgi page source --
# names each of the 45 fields in one row of `matchmx`.
MATCH_COLUMNS = [
    "date", "tourn", "surf", "level", "wl", "player",
    "rank", "seed", "entry", "round",
    "score", "max", "opp", "orank", "oseed", "oentry", "ohand", "obh",
    "obday", "oht", "ocountry", "oactive",
    "tbw", "tbl", "setw", "setl",
    "time", "aces", "dfs", "pts", "firsts", "fwon",
    "swon", "games", "saved", "chances", "oaces", "odfs", "opts", "ofirsts",
    "ofwon", "oswon", "ogames", "osaved", "ochances",
]
# matchhead[22:] -- the counting stats the page sums per player (its own
# `for (var y=22; y<matchhead.length; y++)` accumulation loop).
_SUM_COLUMNS = MATCH_COLUMNS[22:]


def _parse_matchmx(js_text: str) -> list[list[str]]:
    marker = "var matchmx = "
    start = js_text.index(marker) + len(marker)
    data, _ = json.JSONDecoder().raw_decode(js_text, start)
    return data


_NUM_FIELDS = len(MATCH_COLUMNS)


def _normalize_row_length(row: list[str]) -> list[str]:
    """Most rows are exactly 45 fields, but a large minority carry extra
    trailing fields (45 -> 65, or 45 -> 46) that are always empty strings in
    every file checked -- some other part of the site's data pipeline pads
    incomplete-stat matches. Verified empty (never dropped real data) across
    all six source files before trusting this truncate/pad.
    """
    if len(row) == _NUM_FIELDS:
        return row
    if len(row) > _NUM_FIELDS:
        return row[:_NUM_FIELDS]
    return row + [""] * (_NUM_FIELDS - len(row))


def fetch_leaders_matches(tour: str, pool: str = "top50") -> pd.DataFrame:
    """Every match row backing one tour/pool's leaderboards (unfiltered --
    spans several years). Fetch once and reuse across surfaces/stat types
    rather than re-downloading the (1-2.5MB) source file per combination.
    """
    url = LEADERS_SOURCE_URLS[(tour, pool)]
    resp = requests.get(url, headers=_HEADERS, timeout=60)
    resp.raise_for_status()
    rows = [_normalize_row_length(r) for r in _parse_matchmx(resp.text)]
    df = pd.DataFrame(rows, columns=MATCH_COLUMNS)
    df["date"] = pd.to_numeric(df["date"], errors="coerce")  # YYYYMMDD int
    for col in _SUM_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _filter_last_52_weeks(df: pd.DataFrame, as_of: int | None = None) -> pd.DataFrame:
    """Tennis Abstract's own default "Last 52" filter -- NOT a real calendar
    year/364 days, just integer YYYYMMDD arithmetic (`keyday = today - 10000`),
    replicated exactly rather than approximated.
    """
    today = as_of if as_of is not None else int(dt.date.today().strftime("%Y%m%d"))
    return df[df["date"] >= today - 10000]


def _filter_surface(df: pd.DataFrame, surface: str) -> pd.DataFrame:
    if surface == "All":
        return df
    return df[df["surf"] == surface]


def _aggregate_player_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Per-player sums of matchhead[22:] plus win/loss counts and opponent-
    rank list, exactly mirroring the page's `pstats` accumulation loop."""
    grouped = df.groupby("player", as_index=False)[_SUM_COLUMNS].sum(min_count=1)

    decided = df[~df["score"].isin(["W/O", "RET"])]
    wins = decided[decided["wl"] == "W"].groupby("player").size()
    losses = decided[decided["wl"] == "L"].groupby("player").size()

    orank = pd.to_numeric(df["orank"], errors="coerce")
    opp_ranks = df.assign(_orank=orank).dropna(subset=["_orank"]).groupby("player")["_orank"]

    grouped = grouped.set_index("player")
    grouped["wins"] = wins.reindex(grouped.index).fillna(0).astype(int)
    grouped["losses"] = losses.reindex(grouped.index).fillna(0).astype(int)
    grouped["matches"] = grouped["wins"] + grouped["losses"]
    grouped["median_opp_rank"] = opp_ranks.median().reindex(grouped.index)
    grouped["mean_opp_rank"] = opp_ranks.mean().reindex(grouped.index)
    return grouped[grouped["matches"] > 0].reset_index()


def compute_serve_leaders(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Formulas copied from `if (showstats == 'o') {...}` on leaders.cgi.
    `_pct` columns are 0-1 fractions (same convention as `ace_pct` in
    `tennisabstract.parse_surface_speed_html`), not the page's rounded "%"
    display strings.
    """
    a = _aggregate_player_stats(matches_df)
    pts, sgames = a["pts"], a["games"]
    second_serves = pts - a["firsts"]
    holds = sgames - (a["chances"] - a["saved"])
    serve_pts_won = a["fwon"] + a["swon"]

    return pd.DataFrame({
        "player": a["player"],
        "matches": a["matches"], "wins": a["wins"], "losses": a["losses"],
        "match_win_pct": a["wins"] / a["matches"],
        "spw": serve_pts_won / pts,
        "spw_in_play": (serve_pts_won - a["aces"]) / (pts - a["aces"] - a["dfs"]),
        "aces": a["aces"], "ace_pct": a["aces"] / pts,
        "dfs": a["dfs"], "df_pct": a["dfs"] / pts,
        "df_pct_2nd": a["dfs"] / second_serves,
        "first_in_pct": a["firsts"] / pts,
        "first_win_pct": a["fwon"] / a["firsts"],
        "second_win_pct": a["swon"] / second_serves,
        "second_win_pct_in_play": a["swon"] / (second_serves - a["dfs"]),
        "hold_pct": holds / sgames,
        "pts_per_service_game": pts / sgames,
        "pts_lost_per_service_game": (pts - serve_pts_won) / sgames,
    })


def compute_return_leaders(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Formulas copied from `if (showstats == 'w') {...}` on leaders.cgi."""
    a = _aggregate_player_stats(matches_df)
    opts, rgames = a["opts"], a["ogames"]
    vs_serve_pts_won = a["ofwon"] + a["oswon"]
    break_pts_converted = a["ochances"] - a["osaved"]

    return pd.DataFrame({
        "player": a["player"],
        "matches": a["matches"], "wins": a["wins"], "losses": a["losses"],
        "rpw": 1 - vs_serve_pts_won / opts,
        "rpw_in_play": 1 - (vs_serve_pts_won - a["oaces"]) / (opts - a["oaces"] - a["odfs"]),
        "vs_ace_pct": a["oaces"] / opts,
        "vs_df_pct": a["odfs"] / opts,
        "vs_first_win_pct": 1 - a["ofwon"] / a["ofirsts"],
        "vs_second_win_pct": 1 - a["oswon"] / (opts - a["ofirsts"]),
        "break_pct": break_pts_converted / rgames,
        "pts_per_return_game": opts / rgames,
        "pts_won_per_return_game": (opts - a["ofwon"] - a["oswon"]) / rgames,
        "median_opp_rank": a["median_opp_rank"],
        "mean_opp_rank": a["mean_opp_rank"],
    })


def leaders_for(matches_df: pd.DataFrame, stat: str, surface: str = "All") -> pd.DataFrame:
    """`stat`: "serve" or "return". `surface`: one of SURFACES ("All" = no
    filter, matching the page's own default). Applies the page's default
    Last-52-weeks span filter, then the surface filter, then aggregates.
    """
    filtered = _filter_surface(_filter_last_52_weeks(matches_df), surface)
    if stat == "serve":
        return compute_serve_leaders(filtered)
    if stat == "return":
        return compute_return_leaders(filtered)
    raise ValueError(f"Unknown stat type: {stat!r} (expected 'serve' or 'return')")
