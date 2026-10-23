"""Tennis Abstract's live tournament forecasts.

The site keeps one page per running event under /current/ ("2026 ATP Lyon
Results and Forecast"), all linked from its front page. Unlike the player
pages these are server-rendered: the draw projection sits in the page source
as JavaScript strings -- `var projCurrent = '<table>...'` for the rounds
still to play (`proj8`, `proj16`, `proj32` hold the earlier states), one row
per player with the probability of reaching each remaining round -- and
`upcomingSingles` lists the next round's pairings with the head-to-head.

Two players drawn against each other in the next round carry that round's
probability as their chance of winning the match: Cobolli 38.9% to reach the
semi-final, Nakashima 61.1%, together 100%. That is the figure read here.

robots.txt (read 2026-10-23) disallows /jsfrags/, /jsmatches/ and
/jsplayers/, where the per-player match logs and the leaderboard sources
live. This module reads only the front page and the /current/ pages.
"""
from __future__ import annotations

import datetime as dt
import html as html_mod
import logging
import re
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

HOME_URL = "https://www.tennisabstract.com/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)"}
_TIMEOUT = 30
REQUEST_PAUSE = 1.0

_CURRENT_RE = re.compile(r'href="(https?://(?:www\.)?tennisabstract\.com/current/(\d{4})[^"]+\.html)"')
_TITLE_RE = re.compile(r"<title>\s*Tennis Abstract:\s*(\d{4})\s+(.+?)\s+Results and Forecast", re.DOTALL)
_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)%")
# Seeds and entry types in front of a name: "(1)", "(WC)", "(Q)", "(LL)",
# "(PR)", "(SE)", "(Alt)", "(NG)" (next gen), "(JE)", "(ITF)".
_ENTRY_RE = re.compile(r"^(?:\(\s*(?:\d+|WC|Q|LL|PR|SE|Alt|NG|JE|JR|ITF)\s*\)\s*)+", re.IGNORECASE)
_COUNTRY_RE = re.compile(r"\s*\([A-Z]{3}\)\s*$")
_ROUND_LABEL_RE = re.compile(r"\b(R128|R64|R32|R16|QF|SF|F|RR|Q1|Q2|Q3|Q4):\s*")
_H2H_RE = re.compile(r"\[(\d+)-(\d+)\]")


def _var(html: str, name: str) -> str | None:
    m = re.search(r"var %s\s*=\s*'(.*?)';" % re.escape(name), html, re.DOTALL)
    return m.group(1) if m else None


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(_TAG_RE.sub(" ", fragment))).strip()


def clean_name(raw: str) -> str:
    """'(1)Flavio Cobolli (ITA)' -> 'Flavio Cobolli'."""
    name = _text(raw)
    name = _ENTRY_RE.sub("", name)
    name = _COUNTRY_RE.sub("", name)
    return name.strip()


def list_current_events(home_html: str, year: int | None = None) -> list[str]:
    """Forecast pages of the given year linked from the front page, in order."""
    year = year or dt.date.today().year
    out: list[str] = []
    for url, yr in _CURRENT_RE.findall(home_html):
        if int(yr) == year and url not in out:
            out.append(url)
    return out


def parse_projection(table_html: str) -> tuple[list[str], dict[str, dict[str, float]]]:
    """(rounds, {player -> {round -> probability}}) from one projection table.
    A table may restart its header for each half of the draw."""
    rounds: list[str] = []
    probs: dict[str, dict[str, float]] = {}
    for row in _ROW_RE.findall(table_html):
        cells = [_text(c) for c in _CELL_RE.findall(row)]
        if not cells:
            continue
        if cells[0] == "Player":
            rounds = [c for c in cells[1:] if c]
            continue
        name = clean_name(cells[0])
        if not name or name.lower() == "bye":
            continue
        pcts = [round(float(m) / 100.0, 4) for c in cells[1:] for m in _PCT_RE.findall(c)]
        if rounds and len(pcts) == len(rounds):
            probs[name] = dict(zip(rounds, pcts))
    return rounds, probs


def parse_upcoming(fragment: str) -> list[dict]:
    """[{round, player_a, player_b, h2h_a, h2h_b}] from `upcomingSingles`."""
    txt = _text(fragment)
    labels = list(_ROUND_LABEL_RE.finditer(txt))
    out = []
    for i, m in enumerate(labels):
        end = labels[i + 1].start() if i + 1 < len(labels) else len(txt)
        seg = txt[m.end():end].strip()
        if " vs " not in seg:
            continue
        left, right = seg.split(" vs ", 1)
        h2h = _H2H_RE.search(right)
        if h2h:
            right = right[:h2h.start()]
        out.append({
            "round": m.group(1),
            "player_a": clean_name(left),
            "player_b": clean_name(right),
            "h2h_a": int(h2h.group(1)) if h2h else None,
            "h2h_b": int(h2h.group(2)) if h2h else None,
        })
    return out


def parse_event_page(html: str) -> dict:
    """{'tournament', 'year', 'rounds', 'projection', 'matches'} -- `matches`
    carries Tennis Abstract's win probability for every next-round pairing
    whose two reach-the-next-round figures add up to one."""
    title = _TITLE_RE.search(html)
    year = int(title.group(1)) if title else None
    tournament = _text(title.group(2)) if title else None
    proj = _var(html, "projCurrent") or ""
    rounds, probs = parse_projection(proj)
    upcoming = parse_upcoming(_var(html, "upcomingSingles") or "")
    matches = []
    for pairing in upcoming:
        pa = probs.get(pairing["player_a"], {})
        pb = probs.get(pairing["player_b"], {})
        p_a = None
        if rounds:
            nxt = rounds[0]
            a, b = pa.get(nxt), pb.get(nxt)
            if a is not None and b is not None and 0.97 <= a + b <= 1.03:
                p_a = a / (a + b)
        matches.append({**pairing, "p_a": round(p_a, 4) if p_a is not None else None,
                        "next_round": rounds[0] if rounds else None,
                        "title_a": round(pa.get("W"), 4) if pa.get("W") is not None else None,
                        "title_b": round(pb.get("W"), 4) if pb.get("W") is not None else None})
    return {"tournament": tournament, "year": year, "rounds": rounds,
            "projection": probs, "matches": matches}


COLUMNS = ("tournament", "round", "player_a", "player_b", "p_a", "h2h_a", "h2h_b",
           "title_a", "title_b", "url", "fetched_at")


def fetch_forecasts(year: int | None = None, session=None, sleep=time.sleep) -> pd.DataFrame:
    """Every next-round pairing on every current Tennis Abstract forecast page."""
    http = session or requests
    resp = http.get(HOME_URL, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    urls = list_current_events(resp.text, year)
    rows = []
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for url in urls:
        try:
            page = http.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            page.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Tennis Abstract forecast %s unavailable (%s)", url, exc)
            continue
        event = parse_event_page(page.text)
        for m in event["matches"]:
            rows.append({"tournament": event["tournament"], "round": m["round"],
                         "player_a": m["player_a"], "player_b": m["player_b"],
                         "p_a": m["p_a"], "h2h_a": m["h2h_a"], "h2h_b": m["h2h_b"],
                         "title_a": m["title_a"], "title_b": m["title_b"],
                         "url": url, "fetched_at": stamp})
        sleep(REQUEST_PAUSE)
    df = pd.DataFrame(rows, columns=list(COLUMNS))
    logger.info("Tennis Abstract forecasts: %d events, %d pairings (%d with a probability)",
                len(urls), len(df), int(df["p_a"].notna().sum()) if len(df) else 0)
    return df
