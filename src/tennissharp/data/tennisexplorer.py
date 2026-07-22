"""TennisExplorer.com: match schedule + odds, and head-to-head history.

robots.txt (checked 2026-07) only disallows /redirect/, /terms-of-use/, and
/contact/ -- the /matches/ and /mutual/ paths used here are unrestricted.

The schedule page (/matches/) is plain server-rendered HTML (no JS needed),
with a fairly rigid structure: a `<tr class="head flags">` row announces each
tournament, followed by pairs of `<tr id="sNN">`/`<tr id="sNNb">` rows (one
per player) for each match in it. We parse that directly with regex rather
than pandas.read_html, since read_html's positional columns shift depending
on whether a row has an extra "Live streams..." prefix cell.

The head-to-head page (/mutual/<slug1>/<slug2>/), by contrast, is a clean,
uniform table that pandas.read_html handles well directly.
"""
from __future__ import annotations

import io
import re

import pandas as pd
import requests

BASE_URL = "https://www.tennisexplorer.com"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)"}

_TOURNAMENT_RE = re.compile(r'<tr class="head flags">.*?<a href="([^"]+)"[^>]*>.*?<span[^>]*>&nbsp;</span>\s*'
                            r'([^<]+)</a>', re.DOTALL)
_ROW_RE = re.compile(r'<tr id="([a-z]\d+)(b?)"[^>]*>(.*?)</tr>', re.DOTALL)
_PLAYER_RE = re.compile(r'<td class="t-name"><a href="(/player/[^"]+)/">([^<]+)</a>')
_ODDS_RE = re.compile(r'<td class="course\w*"[^>]*>([\d.]+)</td>')
_MATCH_ID_RE = re.compile(r'/match-detail/\?id=(\d+)')


def _extract_tournament_sections(html: str) -> list[tuple[int, str, str]]:
    """Returns [(char_offset, tournament_name, tournament_url), ...] in
    document order, so match rows can be attributed to the section they
    fall under."""
    sections = []
    for m in re.finditer(r'<tr class="head flags">', html):
        block = html[m.start():m.start() + 400]
        link = re.search(r'<a href="([^"]+)"[^>]*>', block)
        # Tournament name is the link's visible text, stripped of the two
        # leading flag/type spans.
        name = re.search(r'</span><span[^>]*>&nbsp;</span>([^<]+)</a>', block)
        if link and name:
            sections.append((m.start(), name.group(1).strip(), BASE_URL + link.group(1)))
    return sections


def _tournament_for_offset(sections: list[tuple[int, str, str]], offset: int) -> tuple[str, str]:
    current = ("Unknown", "")
    for start, name, url in sections:
        if start > offset:
            break
        current = (name, url)
    return current


def parse_matches_html(html: str) -> pd.DataFrame:
    sections = _extract_tournament_sections(html)
    rows = []
    pending: dict | None = None

    for m in _ROW_RE.finditer(html):
        row_id, is_continuation, body = m.group(1), m.group(2), m.group(3)
        player_match = _PLAYER_RE.search(body)
        if not player_match:
            continue
        player_slug = player_match.group(1).rsplit("/", 1)[-1]
        player_name = player_match.group(2).strip()

        if not is_continuation:
            tournament, tournament_url = _tournament_for_offset(sections, m.start())
            odds = _ODDS_RE.findall(body)
            match_id = _MATCH_ID_RE.search(body)
            pending = {
                "tournament": tournament,
                "tournament_url": tournament_url,
                "player1": player_name,
                "player1_slug": player_slug,
                "odds1": float(odds[0]) if len(odds) > 0 else None,
                "odds2": float(odds[1]) if len(odds) > 1 else None,
                "match_id": match_id.group(1) if match_id else None,
            }
        elif pending is not None:
            pending["player2"] = player_name
            pending["player2_slug"] = player_slug
            rows.append(pending)
            pending = None

    return pd.DataFrame(rows)


def fetch_matches(day_offset: int = 0) -> pd.DataFrame:
    """`day_offset=0` is today, `1` tomorrow, `-1` yesterday (results)."""
    url = f"{BASE_URL}/matches/" if day_offset == 0 else f"{BASE_URL}/matches/?type=all&timezone=0&day={day_offset}"
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_matches_html(resp.text)


_H2H_COLUMN_MAP = {
    "Year": "year", "Tournament": "tournament", "Match": "player",
    "S": "sets_won", "Surface": "surface", "Round": "round",
}


def parse_head_to_head_html(html: str) -> pd.DataFrame:
    tables = pd.read_html(io.StringIO(html))
    # The match-history table is the one with a "Match"/"Round" column pair;
    # other tables on the page are player bios, tournament-by-tournament
    # summaries, and unrelated sidebar widgets.
    for table in tables:
        cols = set(table.columns.astype(str))
        if {"Match", "Round", "Year"} <= cols:
            data = table.rename(columns=_H2H_COLUMN_MAP)
            data["player"] = data["player"].astype(str).str.replace("\xa0", " ", regex=False)
            return data.reset_index(drop=True)
    return pd.DataFrame()


def fetch_head_to_head(slug1: str, slug2: str) -> pd.DataFrame:
    """Full match history between two players. Slugs come from
    `fetch_matches()`'s player1_slug/player2_slug columns (e.g. "zverev-6f768").
    """
    resp = requests.get(f"{BASE_URL}/mutual/{slug1}/{slug2}/", headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_head_to_head_html(resp.text)


def head_to_head_summary(h2h_df: pd.DataFrame, player1: str, player2: str) -> tuple[int, int]:
    """(player1_wins, player2_wins) counted from the match-history rows --
    each match contributes two rows (one per player); `sets_won` > half the
    match's total sets identifies that row's player as the winner.
    """
    if h2h_df.empty:
        return 0, 0
    wins = {player1: 0, player2: 0}
    for _, group in h2h_df.groupby(h2h_df.index // 2):
        if len(group) != 2:
            continue
        winner_row = group.loc[group["sets_won"].idxmax()]
        name = winner_row["player"]
        for p in (player1, player2):
            if p in name or name in p:
                wins[p] += 1
                break
    return wins[player1], wins[player2]
