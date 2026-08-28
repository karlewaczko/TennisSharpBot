"""TennisExplorer.com: match schedule + odds + results, head-to-head
history, and per-bookmaker odds-movement history ("Quotenverlauf").

robots.txt (checked 2026-07) only disallows /redirect/, /terms-of-use/, and
/contact/ -- the /matches/, /mutual/, and /match-detail/ paths used here are
unrestricted.

The schedule page (/matches/) is plain server-rendered HTML (no JS needed),
with a fairly rigid structure: a `<tr class="head flags">` row announces each
tournament, followed by pairs of `<tr id="sNN">`/`<tr id="sNNb">` rows (one
per player) for each match in it. We parse that directly with regex rather
than pandas.read_html, since read_html's positional columns shift depending
on whether a row has an extra "Live streams..." prefix cell. The same rows
carry the final score once a match has been played (`day_offset<0`, or any
match that's since finished), so `fetch_matches()` doubles as the results feed.

The head-to-head page (/mutual/<slug1>/<slug2>/), by contrast, is a clean,
uniform table that pandas.read_html handles well directly.

The match-detail page (/match-detail/?id=<id>) embeds each bookmaker's full
odds history (current odds plus every recorded change, oldest one marked
"Opening odds") directly in its odds-comparison table -- nested tables
inside table cells, so `fetch_match_odds_history()` depth-counts
`<table>`/`</table>` tags to isolate it rather than using a non-greedy regex
(which would stop at the first nested `</tr>`/`</table>` it hit).
"""
from __future__ import annotations

import datetime as dt
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
# Present on both scheduled rows (empty placeholders) and finished ones
# (actual values), so the same regex covers upcoming and past-day fetches.
_RESULT_RE = re.compile(r'<td class="result">([^<]*)</td>')
_SCORE_CELL_RE = re.compile(r'<td class="score">([^<]*)</td>')


# The columns parse_matches_html emits, in the order it builds them.
MATCH_COLUMNS = ("tournament", "tournament_url", "player1", "player1_slug",
                 "odds1", "odds2", "match_id", "sets_won1", "player2",
                 "player2_slug", "sets_won2", "score")


def _clean_cell(text: str | None) -> str | None:
    """Strip the site's non-breaking-space placeholder (sometimes missing
    its trailing semicolon, a site-side markup bug) down to None."""
    if text is None:
        return None
    cleaned = text.replace("&nbsp;", "").replace("&nbsp", "").strip()
    return cleaned or None


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
            result = _RESULT_RE.search(body)
            pending = {
                "tournament": tournament,
                "tournament_url": tournament_url,
                "player1": player_name,
                "player1_slug": player_slug,
                "odds1": float(odds[0]) if len(odds) > 0 else None,
                "odds2": float(odds[1]) if len(odds) > 1 else None,
                "match_id": match_id.group(1) if match_id else None,
                "sets_won1": _clean_cell(result.group(1)) if result else None,
                "_score_cells1": [_clean_cell(c) for c in _SCORE_CELL_RE.findall(body)],
            }
        elif pending is not None:
            result = _RESULT_RE.search(body)
            score_cells1 = pending.pop("_score_cells1")
            score_cells2 = [_clean_cell(c) for c in _SCORE_CELL_RE.findall(body)]
            sets = []
            for g1, g2 in zip(score_cells1, score_cells2):
                if g1 is None or g2 is None:
                    break
                sets.append(f"{g1}-{g2}")
            pending["player2"] = player_name
            pending["player2_slug"] = player_slug
            pending["sets_won2"] = _clean_cell(result.group(1)) if result else None
            pending["score"] = " ".join(sets) if sets else None
            rows.append(pending)
            pending = None

    # A day the site has not filled in yet parses to nothing. Returning a
    # bare DataFrame() there hands callers a frame with no columns at all, so
    # the first `df["score"]` raises instead of yielding an empty selection --
    # fetching three days ahead hits this whenever the last one is still blank.
    df = pd.DataFrame(rows, columns=None if rows else list(MATCH_COLUMNS))
    for col in ("sets_won1", "sets_won2"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def day_for_offset(day_offset: int = 0, today: dt.date | None = None) -> dt.date:
    return (today or dt.date.today()) + dt.timedelta(days=day_offset)


def day_url(day_offset: int = 0, today: dt.date | None = None) -> str:
    """URL of the schedule page `day_offset` days from today.

    The site's `day` parameter is a *calendar day of the month*, not an
    offset: `?day=1` returns the 1st, whatever today is. Read as an offset it
    silently returns the wrong date -- `fetch_matches(1)` pulled the 1st of
    August into the upcoming-matches file, 197 finished matches that then
    reached the value table carrying their pre-match odds. The date has to be
    spelled out in full: year, month and day together.
    """
    day = day_for_offset(day_offset, today)
    return (f"{BASE_URL}/matches/?type=all&timezone=0"
            f"&year={day.year}&month={day.month:02d}&day={day.day:02d}")


def fetch_matches(day_offset: int = 0) -> pd.DataFrame:
    """`day_offset=0` is today, `1` tomorrow, `-1` yesterday (results).

    Rows carry a `date` column: one page is one calendar day, and without it
    a file assembled from several pages cannot say which day a match belongs
    to -- the rows themselves hold no date at all.
    """
    day = day_for_offset(day_offset)
    resp = requests.get(day_url(day_offset), headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    df = parse_matches_html(resp.text)
    df["date"] = day.isoformat()
    return df


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


_ODDS_TABLE_ANCHOR = '<table class="result " cellspacing="0">'  # trailing space distinguishes
# this from the H2H match-history table above, which is class="result" (no space).
_BOOKMAKER_ROW_START_RE = re.compile(r'<tr class="(?:one|two)">')
_BOOKMAKER_NAME_RE = re.compile(r'<span class="t">([^<]+)</span>')
_ODDS_MOVE_RE = re.compile(r'<tr><td>([^<]+)</td><td class="bold">([^<]+)</td><td class="diff-\w+">([^<]*)</td></tr>')
_OPENING_MARKER = '<td colspan="3" class="title">Opening odds</td>'


def _extract_balanced_table(html: str, start: int) -> str:
    """Slice out a `<table>...</table>` region honoring nested tables (the
    odds-comparison table embeds one small history table per bookmaker per
    player inside it), by depth-counting `<table`/`</table>` occurrences
    rather than stopping at the first `</table>`.
    """
    depth, i = 0, start
    while True:
        next_open = html.find("<table", i)
        next_close = html.find("</table>", i)
        if next_close == -1:
            raise ValueError("Unbalanced <table> while scanning odds-comparison table")
        if next_open != -1 and next_open < next_close:
            depth += 1
            i = next_open + len("<table")
        else:
            depth -= 1
            i = next_close + len("</table>")
            if depth == 0:
                return html[start:i]


def _resolve_odds_timestamp(raw: str, reference: dt.date) -> pd.Timestamp:
    """The site prints "DD.MM. HH:MM" with no year. Assume `reference`'s
    year, then roll back a year if that lands more than 2 days in the
    future (handles scraping in January about odds recorded the preceding
    December)."""
    import datetime as dt

    day_str, time_str = raw.strip().split(" ", 1)
    day, month = (int(x) for x in day_str.rstrip(".").split("."))
    hour, minute = (int(x) for x in time_str.split(":"))
    candidate = dt.datetime(reference.year, month, day, hour, minute)
    if candidate > dt.datetime.combine(reference, dt.time(23, 59)) + dt.timedelta(days=2):
        candidate = candidate.replace(year=reference.year - 1)
    return pd.Timestamp(candidate)


def parse_odds_history_html(html: str, reference_date: dt.date | None = None) -> pd.DataFrame:
    """Long-format odds-movement timeline ("Quotenverlauf"): one row per
    (bookmaker, player, recorded change). The match-detail page embeds each
    bookmaker's full odds history (newest first, ending in an "Opening
    odds"-marked oldest entry) directly in its odds-comparison table, so no
    separate request/page is needed.
    """
    import datetime as dt

    reference_date = reference_date or dt.date.today()
    anchor = html.find(_ODDS_TABLE_ANCHOR)
    if anchor == -1:
        return pd.DataFrame()
    table_html = _extract_balanced_table(html, anchor)

    header_m = re.search(r'<tr class="head">.*?<td class="k1">([^<]+)</td>\s*'
                          r'<td class="k2">([^<]+)</td>', table_html, re.DOTALL)
    if not header_m:
        return pd.DataFrame()
    player1, player2 = header_m.group(1).strip(), header_m.group(2).strip()

    row_starts = [m.start() for m in _BOOKMAKER_ROW_START_RE.finditer(table_html)]
    rows = []
    for idx, start in enumerate(row_starts):
        end = row_starts[idx + 1] if idx + 1 < len(row_starts) else len(table_html)
        block = table_html[start:end]
        name_m = _BOOKMAKER_NAME_RE.search(block)
        if not name_m:
            continue
        bookmaker = name_m.group(1).strip()

        k1_pos, k2_pos = block.find('<td class="k1">'), block.find('<td class="k2">')
        if k1_pos == -1 or k2_pos == -1:
            continue
        regions = {player1: block[k1_pos:k2_pos], player2: block[k2_pos:]}

        for player, region in regions.items():
            opening_pos = region.find(_OPENING_MARKER)
            for m in _ODDS_MOVE_RE.finditer(region):
                rows.append({
                    "bookmaker": bookmaker,
                    "player": player,
                    "timestamp": _resolve_odds_timestamp(m.group(1), reference_date),
                    "odds": float(m.group(2)),
                    "is_opening": opening_pos != -1 and m.start() > opening_pos,
                })

    df = pd.DataFrame(rows)
    return df.sort_values(["bookmaker", "player", "timestamp"]).reset_index(drop=True) if not df.empty else df


# The match-detail header, e.g.
#   <div class="box boxBasic lGray"><span class="upper">Today</span>, 17:00,
#   <a href="/us-open/2026/atp-men/">US Open</a>, Qualification - 3. round, hard
# The schedule page carries none of this: qualifying and main draw share a
# tournament name AND a URL there, and the surface is never stated at all.
# The text runs to the next tag, not to </div> -- a Facebook <iframe>
# follows it immediately inside the same box.
_CONTEXT_RE = re.compile(
    r'<div class="box boxBasic[^"]*">.*?</a>\s*,\s*([^<]+)', re.DOTALL)

QUALIFYING_MARKERS = ("qualification", "qualifying", "qualif")


def parse_match_context_html(html: str) -> dict:
    """{'round': str|None, 'is_qualifying': bool, 'surface': str|None}

    Round and surface both matter for scoring. Men's Grand Slam *qualifying*
    is best of three while the main draw is best of five, and nothing on the
    schedule page distinguishes them -- 70 finished US Open qualifying
    matches were scored as five-setters before this existed.
    """
    out = {"round": None, "is_qualifying": False, "surface": None}
    m = _CONTEXT_RE.search(html)
    if not m:
        return out
    # "Qualification - 3. round, hard" -> round part, surface part.
    tail = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",")
    parts = [p.strip() for p in tail.split(",") if p.strip()]
    if not parts:
        return out
    out["surface"] = parts[-1].title() if len(parts) > 1 else None
    out["round"] = parts[0] if len(parts) > 1 else tail
    lowered = (out["round"] or "").lower()
    out["is_qualifying"] = any(k in lowered for k in QUALIFYING_MARKERS)
    return out


def _fetch_match_detail_html(match_id: str | int) -> str:
    resp = requests.get(f"{BASE_URL}/match-detail/?id={match_id}", headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_match_context(match_id: str | int) -> dict:
    return parse_match_context_html(_fetch_match_detail_html(match_id))


def fetch_match_detail(match_id: str | int) -> tuple[pd.DataFrame, dict]:
    """(odds history, context) from a single request.

    Both live on the same page, and a full card is a few hundred of these --
    fetching it twice would double the slowest part of a dashboard build.
    """
    html = _fetch_match_detail_html(match_id)
    return parse_odds_history_html(html), parse_match_context_html(html)


def fetch_match_odds_history(match_id: str | int) -> pd.DataFrame:
    """Odds-movement timeline for one match, straight from its match-detail
    page (`match_id` comes from `fetch_matches()`'s `match_id` column).
    """
    resp = requests.get(f"{BASE_URL}/match-detail/?id={match_id}", headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_odds_history_html(resp.text)


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
