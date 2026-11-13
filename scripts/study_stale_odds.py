#!/usr/bin/env python3
"""After a big pre-match move at a sharp venue, how long does bet365 keep
the old price, and what is that price worth? NBA, NHL and football
(soccer); moneylines, spreads and totals; Polymarket and Kalshi as the
sharp venues, and which of the two moves first. BetExplorer has no
American football, so the NFL cannot be checked this way.

    python scripts/study_stale_odds.py --days 6

Prices: Polymarket's minute prices (CLOB prices-history) and Kalshi's minute
candles (the middle of bid and ask), against BetExplorer's odds histories
(each bookmaker's changes, to the minute):
- BetExplorer serves the bookmakers licensed where the visitor is. From
  this machine and GitHub's runners (US) that is bet365.us, not bet365.com:
  the same company's trading, not the same price list. Pinnacle and Betfair
  are not shown to a US visitor; for tennis, scripts/study_pm_leadlag.py has
  them from TennisExplorer.
- BetExplorer's times are Prague time (as TennisExplorer's).
- A move: a venue's price shifts --jump or more within 30 minutes and holds
  it three hours on (as scripts/study_pm_leadlag.py).
- bet365's reaction: when its chance (margin taken out over the outcomes)
  first stood half way between its level an hour before the move and three
  hours on. A history records a change when BetExplorer saw it, so the lag
  is an upper bound.
- Value: bet365's price for the side that rose, a minute after the venue
  crossed half way, at that venue's last price before the start as the fair
  chance: fair x odds - 1. No tax.

Results go to data/reports/stale_odds_bet365.json. Robots: BetExplorer
disallows /ad/, /redirect/, /bookmaker/ and query paging; none is used.
One request at a time, a pause between them, the project's user agent;
BetExplorer's answers are kept under data/raw/betexplorer so a rerun asks
again only for what it has not seen.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import time
import unicodedata

import numpy as np
import pandas as pd
import requests

from tennissharp import config
from tennissharp.data import polymarket_traders as pt

GAMMA, CLOB, BE = pt.GAMMA_API, "https://clob.polymarket.com/prices-history", "https://www.betexplorer.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)"}
CLOCK = "Europe/Prague"
WINDOW, BEFORE, AFTER = pd.Timedelta(minutes=30), pd.Timedelta(hours=1), pd.Timedelta(hours=3)
PAUSE, KALSHI_PAUSE = 1.5, 0.7     # seconds between requests to BetExplorer and Kalshi
MIN_VOLUME = {"moneyline": 50000.0, "spreads": 20000.0, "totals": 20000.0}   # Polymarket dollars
LINES_PER_TYPE = 2                 # spread and total lines per venue and match
MAX_GAP = 0.15                     # bet365's chance this far from the venue's: a mapping error
CACHE = config.RAW_DIR / "betexplorer"
OUT = config.REPORTS_DIR / "stale_odds_bet365.json"
# Polymarket league code -> (sport, Gamma tag, BetExplorer results page, BetExplorer moneyline type, Kalshi series stem)
LEAGUES = {
    "nba": ("basketball", 745, "/basketball/usa/nba/results/", "ha", "NBA"),
    "nhl": ("ice hockey", 899, "/hockey/usa/nhl/results/", "ha", "NHL"),
    "epl": ("football", 82, "/football/england/premier-league/results/", "1x2", "EPL"),
    "lal": ("football", 780, "/football/spain/laliga/results/", "1x2", "LALIGA"),
    "bun": ("football", 1494, "/football/germany/bundesliga/results/", "1x2", "BUNDESLIGA"),
    "sea": ("football", 101962, "/football/italy/serie-a/results/", "1x2", "SERIEA"),
    "fl1": ("football", 102070, "/football/france/ligue-1/results/", "1x2", "LIGUE1"),
    "ucl": ("football", 100977, "/football/europe/champions-league/results/", "1x2", "UCL"),
    "uel": ("football", 101787, "/football/europe/europa-league/results/", "1x2", "UEL"),
}
GAME = re.compile(r"^([a-z0-9]+)-[a-z0-9]+-[a-z0-9]+-(\d{4}-\d{2}-\d{2})$")
STOP = {"fc", "cf", "afc", "sc", "ac", "club", "the", "cd", "ud", "de", "fk", "sk", "bc", "calcio", "ssc", "as"}
COLUMNS = {"ha": {"home": 0, "away": 1}, "1x2": {"home": 0, "draw": 1, "away": 2},
           "ou": {"over": 0, "under": 1}, "ah": {"home": 0, "away": 1}}
OTHER = {"home": "away", "away": "home", "over": "under", "under": "over"}


def _get(url, params=None, headers=None, tries=4, pause=0.0):
    for i in range(tries):
        time.sleep(pause)
        try:
            r = requests.get(url, params=params, headers={**HEADERS, **(headers or {})}, timeout=30)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 404):
                return None
        except requests.RequestException:
            pass
        time.sleep(2.0 * (i + 1))
    return None


def be_get(path, ref=None, ajax=False) -> str | None:
    """A BetExplorer answer's text, from the cache when it has been seen;
    results pages are always asked fresh."""
    key = CACHE / (hashlib.sha1(path.encode()).hexdigest() + ".txt")
    if "/results/" not in path and key.exists():
        return key.read_text()
    h = {"Referer": BE + ref} if ref else {}
    if ajax:
        h["X-Requested-With"] = "XMLHttpRequest"
    r = _get(BE + path, headers=h, pause=PAUSE)
    if r is None:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    key.write_text(r.text)
    return r.text


# --- names ----------------------------------------------------------------

def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(w for w in re.sub(r"[^a-z0-9 ]", " ", s).split() if w not in STOP)


def _score(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    if ta <= tb or tb <= ta:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def side_of(team: str, match: dict) -> str | None:
    """'home' or 'away': which of BetExplorer's two teams a name is."""
    h, a = _score(team, match["home"]), _score(team, match["away"])
    if max(h, a) < 0.55 or h == a:
        return None
    return "home" if h > a else "away"


# --- BetExplorer ----------------------------------------------------------

def results(path: str) -> list[dict]:
    """A league's recent results: id, both names (home first), the day."""
    html = be_get(path)
    if not html:
        return []
    out, today = [], pd.Timestamp.now(tz=CLOCK).normalize()
    for m in re.finditer(r'<a[^>]*href="([^"]+/([A-Za-z0-9]{8})/)"[^>]*class="in-match"[^>]*>(.*?)</a>(.*?)</tr>', html, re.S):
        names = [re.sub(r"<[^>]+>", "", x).strip() for x in m[3].split(" - ")]
        when = re.findall(r'h-text-no-wrap">([^<]+)<', m[4])
        if len(names) != 2 or not when:
            continue
        w = when[-1].strip()
        if w in ("Today", "Yesterday"):
            day = today - pd.Timedelta(days=int(w == "Yesterday"))
        else:
            d = re.match(r"(\d{2})\.(\d{2})\.(\d{4})?", w)
            if not d:
                continue
            year = int(d[3]) if d[3] else today.year
            day = pd.Timestamp(year=year, month=int(d[2]), day=int(d[1]), tz=CLOCK)
            if day > today + pd.Timedelta(days=1):
                day = day.replace(year=year - 1)
        out.append({"url": m[1], "id": m[2], "home": names[0], "away": names[1], "day": day})
    return out


def find_match(teams: list[str], day: pd.Timestamp, games: list[dict]):
    """The BetExplorer match of two teams around a day (either order)."""
    best = None
    for g in games:
        if abs((g["day"] - day).days) > 1:
            continue
        for a, b in ((teams[0], teams[1]), (teams[1], teams[0])):
            s1, s2 = _score(a, g["home"]), _score(b, g["away"])
            if min(s1, s2) >= 0.55 and (best is None or s1 + s2 > best[0]):
                best = (s1 + s2, g)
    return best[1] if best else None


def _attrs(tag: str) -> dict:
    return dict(re.findall(r'([\w-]+)="([^"]*)"', tag))


def bet365_cells(match: dict, bt: str) -> dict:
    """bet365's cells of one bet type, by line ('' for a moneyline)."""
    text = be_get(f"/match-odds/{match['id']}/0/{bt}/odds/?lang=en", ref=match["url"], ajax=True)
    try:
        html = json.loads(text).get("odds", "") if text else ""
    except ValueError:
        html = ""
    blocks = re.findall(r'<tbody id="all-odds-([^"]*)"[^>]*>(.*?)</tbody>', html, re.S) or [("", html)]
    out = {}
    for line, body in blocks:
        for row in re.findall(r"<tr\s+data-bid=\"\d+\"[^>]*>.*?</tr>", body, re.S):
            if "bet365" in row.lower():
                cells = [_attrs(c) for c in re.findall(r'<td([^>]*data-odd="[^"]*"[^>]*)>', row)]
                if cells:
                    out[line] = cells
    return out


def _local(year, month, day, hour, minute):
    t = pd.Timestamp(year=year, month=month, day=day, hour=hour, minute=minute)
    return t.tz_localize(CLOCK, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def cell_history(cell: dict, match: dict, year: int) -> pd.Series:
    """One outcome's bet365 odds over time (UTC): the archive plus the current price."""
    path = "/archive-odds/{}/{}/{}/{}/{}/".format(*(cell.get(k, "") for k in ("data-oid", "data-bid", "data-bt", "data-sc", "data-hcp")))
    text = be_get(path, ref=match["url"], ajax=True)
    try:
        rows = json.loads(text) if text else []
    except ValueError:
        rows = []
    pts = {}
    for x in rows if isinstance(rows, list) else []:
        d = re.match(r"(\d{2})\.(\d{2})\.\s*(\d{2}):(\d{2})", str(x.get("date", "")).strip())
        if d:
            pts[_local(year, int(d[2]), int(d[1]), int(d[3]), int(d[4]))] = float(x["odd"])
    c = re.match(r"(\d+),(\d+),(\d+),(\d+),(\d+)", cell.get("data-created", ""))
    if c and cell.get("data-odd"):
        pts[_local(int(c[3]), int(c[2]), int(c[1]), int(c[4]), int(c[5]))] = float(cell["data-odd"])
    s = pd.Series(pts, dtype=float)
    return s[s.index.notna()].sort_index()


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class Bet365:
    """bet365's histories of one match, by bet type and line, fetched once."""

    def __init__(self, match: dict, year: int):
        self.match, self.year, self.tables, self.hist = match, year, {}, {}

    def lines(self, bt: str) -> dict:
        if bt not in self.tables:
            self.tables[bt] = bet365_cells(self.match, bt)
        return self.tables[bt]

    def series(self, bt: str, line) -> list[pd.Series] | None:
        """Each outcome's odds over time, in the table's column order."""
        cells = self.lines(bt)
        if line == "":
            row = cells.get("") or (next(iter(cells.values())) if len(cells) == 1 else None)
        else:
            row = next((v for k, v in cells.items() if _num(k) is not None and abs(_num(k) - line) < 1e-6), None)
        if not row or len(row) < len(COLUMNS[bt]):
            return None
        key = (bt, line)
        if key not in self.hist:
            self.hist[key] = [cell_history(c, self.match, self.year) for c in row[:len(COLUMNS[bt])]]
        return self.hist[key]


def fair_chances(series: list[pd.Series]) -> list[pd.Series]:
    """Each outcome's chance with bet365's margin taken out, at every change."""
    w = pd.concat(series, axis=1, sort=True).ffill().dropna()
    inv = 1 / w
    return [inv[i] / inv.sum(axis=1) for i in range(len(series))]


# --- the sharp venues -----------------------------------------------------

def pm_events(code: str, tag: int, days: int, now: pd.Timestamp) -> list[dict]:
    """Polymarket's matches of a league that started within `days`, with their markets."""
    out, seen = [], set()
    for offset in range(0, 1500, 100):
        r = _get(f"{GAMMA}/events", {"tag_id": tag, "closed": "true", "limit": 100, "offset": offset,
                                     "order": "endDate", "ascending": "false"})
        rows = r.json() if r is not None else []
        if not isinstance(rows, list) or not rows:
            break
        old = 0
        for e in rows:
            m = GAME.match(e.get("slug", ""))
            start = pd.Timestamp(e.get("startTime") or e.get("endDate") or "1970-01-01T00:00:00Z")
            start = start.tz_localize("UTC") if start.tzinfo is None else start
            if start < now - pd.Timedelta(days=days):
                old += 1
                continue
            if m and m[1] == code and e["slug"] not in seen and start <= now:
                seen.add(e["slug"])
                out.append({**e, "start": start})
        if old == len(rows):
            break
    if LEAGUES[code][3] == "1x2":                      # football keeps spreads and totals on a second event
        for e in out:
            r = _get(f"{GAMMA}/events", {"slug": e["slug"] + "-more-markets"})
            more = r.json() if r is not None else []
            if isinstance(more, list) and more:
                e["markets"] = list(e.get("markets") or []) + list(more[0].get("markets") or [])
    return out


def _tokens(m):
    try:
        return json.loads(m.get("clobTokenIds") or "[]")
    except ValueError:
        return []


def pm_history(token: str, start: pd.Timestamp) -> pd.Series:
    r = _get(CLOB, {"market": token, "fidelity": 1, "startTs": int((start - pd.Timedelta(hours=36)).timestamp()),
                    "endTs": int(start.timestamp())}, pause=0.2)
    pts = (r.json() or {}).get("history", []) if r is not None else []
    return pd.Series({pd.Timestamp(int(x["t"]), unit="s", tz="UTC"): float(x["p"]) for x in pts}, dtype=float).sort_index()


def pm_markets(e: dict, match: dict, code: str) -> list[dict]:
    """Polymarket's markets of a match, each described in bet365's terms:
    bet type, line, and which column outcome 0 (and outcome 1) is."""
    ms = [m for m in e.get("markets") or [] if len(_tokens(m)) == 2]
    vol = lambda m: float(m.get("volumeNum") or 0)  # noqa: E731
    out = []
    for kind in ("moneyline", "spreads", "totals"):
        group = sorted([m for m in ms if m.get("sportsMarketType") == kind and vol(m) >= MIN_VOLUME[kind]], key=vol, reverse=True)
        for m in group if kind == "moneyline" else group[:LINES_PER_TYPE]:
            q, outs = m.get("question") or "", json.loads(m.get("outcomes") or "[]")
            if kind == "moneyline" and LEAGUES[code][3] == "1x2":
                if re.search(r"\bdraw\b", q, re.I):
                    desc = ("1x2", "", "draw", None)
                else:
                    s = side_of(re.sub(r"^Will\s+|\s+win.*$", "", q).strip(), match)
                    desc = ("1x2", "", s, None) if s else None
            elif kind == "moneyline":
                s = side_of(outs[0], match) if outs else None
                desc = ("ha", "", s, OTHER[s]) if s else None
            elif kind == "totals" and m.get("line") is not None:
                desc = ("ou", float(m["line"]), "over", "under")
            elif kind == "spreads" and m.get("line") is not None and outs:
                s = side_of(outs[0], match)
                line = float(m["line"])
                desc = ("ah", line if s == "home" else -line, s, OTHER[s]) if s else None
            else:
                desc = None
            if desc:
                out.append({"venue": "Polymarket", "kind": kind, "label": q, "desc": desc,
                            "get": (lambda tok=_tokens(m)[0], st=e["start"]: pm_history(tok, st))})
    return out


def kalshi_markets(stem: str, days: int, now: pd.Timestamp) -> dict:
    """Kalshi's settled game, spread and total markets of a league within
    `days`, by match key (the ticker's date and team codes)."""
    out = {}
    for kind, suffix in (("moneyline", "GAME"), ("spreads", "SPREAD"), ("totals", "TOTAL")):
        cursor = None
        for _ in range(20):
            params = {"series_ticker": f"KX{stem}{suffix}", "status": "settled", "limit": 1000,
                      "min_close_ts": int((now - pd.Timedelta(days=days + 1)).timestamp())}
            if cursor:
                params["cursor"] = cursor
            r = _get(f"{KALSHI}/markets", params, pause=KALSHI_PAUSE)
            js = r.json() if r is not None else {}
            for m in js.get("markets", []):
                key = m.get("event_ticker", "").split("-", 1)[-1]          # e.g. 26NOV09BUFMIN
                out.setdefault(key, []).append({**m, "kind": kind, "series": f"KX{stem}{suffix}"})
            cursor = js.get("cursor")
            if not cursor:
                break
    return out


def kalshi_history(m: dict, start: pd.Timestamp) -> pd.Series:
    r = _get(f"{KALSHI}/series/{m['series']}/markets/{m['ticker']}/candlesticks",
             {"start_ts": int((start - pd.Timedelta(hours=36)).timestamp()), "end_ts": int(start.timestamp()),
              "period_interval": 1}, pause=KALSHI_PAUSE)
    pts = {}
    for c in (r.json().get("candlesticks", []) if r is not None else []):
        bid, ask = _num((c.get("yes_bid") or {}).get("close_dollars")), _num((c.get("yes_ask") or {}).get("close_dollars"))
        if bid is not None and ask is not None and 0 < bid <= ask < 1 and ask - bid <= 0.10:
            pts[pd.Timestamp(int(c["end_period_ts"]), unit="s", tz="UTC")] = (bid + ask) / 2
    return pd.Series(pts, dtype=float).sort_index()


def _kalshi_day(key: str):
    d = re.match(r"(\d{2})([A-Z]{3})(\d{2})", key)
    if not d:
        return None
    return pd.Timestamp(f"20{d[1]}-{d[2].title()}-{d[3]}", tz=CLOCK)


def kalshi_for_match(group: list[dict], match: dict, b365: Bet365, code: str) -> list[dict]:
    """Kalshi's markets of a match in bet365's terms; spread and total lines
    only where bet365 offers the same line, the busiest first."""
    out, lines = [], {"spreads": [], "totals": []}
    for m in group:
        title = m.get("title") or ""
        if m["kind"] == "moneyline":
            name = (m.get("yes_sub_title") or re.sub(r"\s+wins.*$", "", title)).strip()
            if name.lower() in ("tie", "draw") or m.get("ticker", "").endswith("-TIE"):
                desc = ("1x2", "", "draw", None) if LEAGUES[code][3] == "1x2" else None
            else:
                s = side_of(name, match)
                desc = (None if not s else ("1x2", "", s, None) if LEAGUES[code][3] == "1x2" else ("ha", "", s, OTHER[s]))
            if desc:
                out.append({"venue": "Kalshi", "kind": "moneyline", "label": title, "desc": desc, "m": m})
        elif m["kind"] == "spreads":
            g = re.match(r"(.+?) wins by (?:over|more than) ([\d.]+)", title)
            s = side_of(g[1], match) if g else None
            if s:
                x = float(g[2])
                lines["spreads"].append((m, ("ah", -x if s == "home" else x, s, OTHER[s])))
        elif m["kind"] == "totals" and re.match(r"^(Full Game:\s*)?over", title, re.I):
            g = re.search(r"over ([\d.]+)", title, re.I)
            if g:
                lines["totals"].append((m, ("ou", float(g[1]), "over", "under")))
    for kind, bt in (("spreads", "ah"), ("totals", "ou")):
        offered = {_num(k) for k in b365.lines(bt)} - {None}
        keep = [(m, d) for m, d in lines[kind] if any(abs(d[1] - v) < 1e-6 for v in offered)]
        keep.sort(key=lambda x: -(_num(x[0].get("volume_fp")) or _num(x[0].get("volume")) or 0))
        out += [{"venue": "Kalshi", "kind": kind, "label": m.get("title"), "desc": d, "m": m} for m, d in keep[:LINES_PER_TYPE]]
    return out


# --- moves ----------------------------------------------------------------

def first_jumps(x: pd.Series, jump: float):
    d = (x - x.shift(freq=WINDOW).reindex(x.index)).dropna()
    out, last = [], None
    for t, v in d[d.abs() >= jump].items():
        if last is None or t - last > pd.Timedelta(hours=3):
            out.append((t, int(np.sign(v))))
            last = t
    return out


def crossing(s: pd.Series, t0, t1, sgn: int, least: float):
    if s.empty:
        return None
    pre, post = s[s.index <= t0], s[s.index <= t1]
    if pre.empty or post.empty or (post.iloc[-1] - pre.iloc[-1]) * sgn < least:
        return None
    mid, w = (pre.iloc[-1] + post.iloc[-1]) / 2, s[(s.index > t0) & (s.index <= t1)]
    hit = w[(w - mid) * sgn >= 0]
    return hit.index[0] if len(hit) else None


def level(s: pd.Series, t):
    if s.empty:
        return np.nan
    s = s[s.index <= t]
    return float(s.iloc[-1]) if len(s) else np.nan


def on_grid(p: pd.Series, cut: pd.Timestamp) -> pd.Series | None:
    if p.empty:                                   # an empty series has no time index to compare
        return None
    p = p[p.index < cut]
    if len(p) < 60:
        return None
    grid = pd.date_range(p.index[0].ceil("min"), cut.floor("min"), freq="min")
    return p.reindex(p.index.union(grid)).ffill().reindex(grid)


def moves(P: pd.Series, jump: float) -> list[dict]:
    """A venue's big pre-match moves on one outcome's minute prices."""
    out = []
    for t, sgn in first_jumps(P, jump):
        t0, t1 = t - BEFORE, min(t + AFTER, P.index[-1])
        if t0 < P.index[0] or t1 - t < WINDOW or (P[t1] - P[t0]) * sgn < jump:
            continue
        t_x = crossing(P, t0, t1, sgn, jump / 2)
        if t_x is not None:
            out.append({"t0": t0, "t1": t1, "sgn": sgn, "t_x": t_x, "move": float((P[t1] - P[t0]) * sgn),
                        "close": float(P.iloc[-1]), "p_at": float(P[t_x])})
    return out


def judge(x: dict, src: dict, b365: Bet365, cut: pd.Timestamp) -> dict:
    """bet365 against one move: how late it followed and what its price was worth."""
    bt, line, pos0, pos1 = src["desc"]
    base = {"venue": src["venue"], "kind": src["kind"], "label": src["label"], "move": round(x["move"], 4),
            "t_x": x["t_x"].isoformat()}
    rising = pos0 if x["sgn"] > 0 else pos1
    if rising is None:
        return {**base, "status": "a football win market that fell: no single bet365 side"}
    hist = b365.series(bt, line)
    if hist is None:
        return {**base, "status": "line not at bet365"}
    if any(h.empty for h in hist):
        return {**base, "status": "no bet365 history"}
    i = COLUMNS[bt][rising]
    q, odds = fair_chances(hist)[i], hist[i]
    fair_close = x["close"] if x["sgn"] > 0 else 1 - x["close"]
    side_now = x["p_at"] if x["sgn"] > 0 else 1 - x["p_at"]
    gap = abs(level(q, x["t_x"]) - side_now)
    if np.isnan(gap):
        return {**base, "status": "no bet365 price yet at the move"}
    if gap > MAX_GAP:
        return {**base, "status": "bet365 chance too far from the venue's", "gap": round(gap, 3)}
    at = x["t_x"] + pd.Timedelta(minutes=1)
    o_stale, o_before, o_close = level(odds, at), level(odds, x["t0"]), level(odds, cut)
    t_b = crossing(q, x["t0"], x["t1"], 1, x["move"] / 3)
    return {**base, "status": "ok", "lag_min": round((t_b - x["t_x"]).total_seconds() / 60, 1) if t_b is not None else None,
            "followed": t_b is not None, "unchanged_at_1min": bool(o_stale == o_before),
            "odds_before": o_before, "odds_stale": o_stale, "odds_close": o_close, "fair_close": round(fair_close, 4),
            "value": round(fair_close * o_stale - 1, 4), "gap": round(gap, 3),
            "beat_bet365_close": round(o_stale / o_close - 1, 4) if o_close else None}


def study_match(match: dict, start: pd.Timestamp, sources: list[dict], jump: float, b365: Bet365) -> tuple[list, list]:
    cut = start - pd.Timedelta(minutes=2)
    rows, grids = [], []
    for src in sources:
        raw = src["get"]() if "get" in src else kalshi_history(src["m"], start)
        P = on_grid(raw, cut)
        if P is None:
            continue
        grids.append((src, P))
        for x in moves(P, jump):
            rows.append({"match": f"{match['home']} - {match['away']}", "start": start.isoformat(), **judge(x, src, b365, cut)})
    # who moves first, Polymarket or Kalshi: the same outcome on both
    pairs = []
    pm = {g[0]["desc"]: g[1] for g in grids if g[0]["venue"] == "Polymarket"}
    ks = {g[0]["desc"]: g[1] for g in grids if g[0]["venue"] == "Kalshi"}
    for desc in set(pm) & set(ks):
        for who, P in (("Polymarket", pm[desc]), ("Kalshi", ks[desc])):
            for x in moves(P, jump):
                a = crossing(pm[desc], x["t0"], x["t1"], x["sgn"], jump / 2)
                b = crossing(ks[desc], x["t0"], x["t1"], x["sgn"], jump / 2)
                if a is not None and b is not None:
                    pairs.append({"found_in": who, "kind": "spreads" if desc[0] == "ah" else "totals" if desc[0] == "ou" else "moneyline",
                                  "kalshi_after_polymarket_min": round((b - a).total_seconds() / 60, 1), "t": x["t_x"].isoformat()})
    return rows, pairs


def summary(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("status") == "ok"]
    out = {"moves": len(rows), "with_bet365": len(ok)}
    if ok:
        v = np.array([r["value"] for r in ok])
        lags = np.array([r["lag_min"] for r in ok if r["lag_min"] is not None])
        out.update({
            "bet365_followed": round(float(np.mean([r["followed"] for r in ok])), 3),
            "lag_median_min": round(float(np.median(lags)), 1) if len(lags) else None,
            "lag_over_5_min": round(float(np.mean(lags > 5)), 3) if len(lags) else None,
            "unchanged_a_minute_after": round(float(np.mean([r["unchanged_at_1min"] for r in ok])), 3),
            "value_mean": round(float(v.mean()), 4), "value_median": round(float(np.median(v)), 4),
            "value_positive": round(float(np.mean(v > 0)), 3), "value_over_2pct": round(float(np.mean(v > 0.02)), 3),
            "value_mean_when_unchanged": (round(float(np.mean([r["value"] for r in ok if r["unchanged_at_1min"]])), 4)
                                          if any(r["unchanged_at_1min"] for r in ok) else None)})
    out["not_counted"] = {s: sum(1 for r in rows if r.get("status") == s) for s in {r.get("status") for r in rows} - {"ok"}}
    return out


def lead(pairs: list[dict]) -> dict:
    x = np.array([p["kalshi_after_polymarket_min"] for p in pairs], dtype=float)
    if not len(x):
        return {"n": 0}
    return {"n": int(len(x)), "median_min": round(float(np.median(x)), 1), "polymarket_first": round(float(np.mean(x > 1)), 3),
            "same_minute": round(float(np.mean(np.abs(x) <= 1)), 3), "kalshi_first": round(float(np.mean(x < -1)), 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=6)
    ap.add_argument("--jump", type=float, default=0.03)
    ap.add_argument("--leagues", default=",".join(LEAGUES))
    args = ap.parse_args()
    now = pd.Timestamp.now(tz="UTC")
    rows, pairs, counts = [], [], {}
    for code in args.leagues.split(","):
        sport, tag, path, _, stem = LEAGUES[code]
        evs, games, kal = pm_events(code, tag, args.days, now), results(path), kalshi_markets(stem, args.days, now)
        counts[code] = {"polymarket": len(evs), "betexplorer": len(games), "kalshi": len(kal), "studied": 0}
        print(f"{code}: Polymarket {len(evs)}, BetExplorer {len(games)}, Kalshi {len(kal)} matches", flush=True)
        for e in evs:
            parts = [x.strip() for x in re.split(r"\s+vs\.?\s+", e.get("title") or "", maxsplit=1)]
            match = find_match(parts, e["start"].tz_convert(CLOCK).normalize(), games) if len(parts) == 2 else None
            if match is None:
                continue
            try:
                b365 = Bet365(match, e["start"].tz_convert(CLOCK).year)
                sources = pm_markets(e, match, code)
                for key, group in kal.items():
                    day = _kalshi_day(key)
                    names = [m.get("yes_sub_title") for m in group if m["kind"] == "moneyline" and not m.get("ticker", "").endswith("-TIE")]
                    if day is not None and abs((day - e["start"].tz_convert(CLOCK).normalize()).days) <= 1 and len(set(names)) >= 2 \
                            and find_match(sorted(set(names))[:2], day, [match]) is not None:
                        sources += kalshi_for_match(group, match, b365, code)
                        break
                r, p = study_match(match, e["start"], sources, args.jump, b365)
                for x in r:
                    x["league"] = code
                rows += r
                pairs += [{**x, "league": code} for x in p]
                counts[code]["studied"] += 1
            except Exception as exc:                            # one odd match must not end the study
                print("  skipped", e.get("slug"), repr(exc), flush=True)
    by = {}
    for r in rows:
        by.setdefault(LEAGUES[r["league"]][0], {}).setdefault(r["venue"], {}).setdefault(r["kind"], []).append(r)
    lead_by = {}
    for p in pairs:
        lead_by.setdefault(LEAGUES[p["league"]][0], {}).setdefault(p["kind"], []).append(p)
    report = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "days": args.days,
              "jump": args.jump, "bookmaker": "bet365.us (BetExplorer from a US address)", "matches": counts,
              "by_sport": {s: {v: {k: summary(x) for k, x in kinds.items()} for v, kinds in venues.items()} for s, venues in by.items()},
              "by_venue": {v: summary([r for r in rows if r["venue"] == v]) for v in ("Polymarket", "Kalshi")},
              "kalshi_vs_polymarket": {s: {k: lead(x) for k, x in kinds.items()} for s, kinds in lead_by.items()},
              "all": summary(rows), "moves": rows, "pairs": pairs}
    OUT.write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: report[k] for k in ("matches", "by_venue", "kalshi_vs_polymarket")}, indent=1, default=str))


if __name__ == "__main__":
    main()
