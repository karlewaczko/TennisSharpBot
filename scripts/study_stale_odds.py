#!/usr/bin/env python3
"""After a big pre-match move on Polymarket, how long does bet365 keep the
old price, and what is that price worth? NBA, NFL, NHL and football
(soccer), moneylines, spreads and totals.

    python scripts/study_stale_odds.py --days 6

Polymarket's minute prices (CLOB prices-history) against BetExplorer's odds
histories (each bookmaker's changes, with the minute):
- BetExplorer serves the bookmakers licensed where the visitor is. From
  this machine and GitHub's runners (US) that is bet365.us, not
  bet365.com: the same company's trading, not the same price list.
- Its times are Prague time (as TennisExplorer's).
- A move: Polymarket's price shifts --jump or more within 30 minutes and
  holds it three hours on (as scripts/study_pm_leadlag.py).
- bet365's reaction: when its chance (margin taken out over the outcomes)
  first stood half way between its level an hour before the move and three
  hours on. A history records a change when BetExplorer saw it, so the lag
  is an upper bound.
- Value: bet365's price for the side that rose, one minute after Polymarket
  crossed half way, at Polymarket's last price before the start as the fair
  chance: fair x odds - 1. Polymarket's closing prices are well calibrated
  (data/reports/prediction_market_sharpness.json).

Results go to data/reports/stale_odds_bet365.json. Robots: BetExplorer
disallows /ad/, /redirect/, /bookmaker/ and query paging; none is used.
One request at a time, a pause between them, the project's user agent.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import difflib
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
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)"}
CLOCK = "Europe/Prague"
WINDOW, BEFORE, AFTER = pd.Timedelta(minutes=30), pd.Timedelta(hours=1), pd.Timedelta(hours=3)
PAUSE = 1.5                     # seconds between BetExplorer requests
MIN_VOLUME = {"moneyline": 50000.0, "spreads": 20000.0, "totals": 20000.0}
LINES_PER_TYPE = 2              # the busiest spread and total lines of a match
OUT = config.REPORTS_DIR / "stale_odds_bet365.json"
# league code on Polymarket -> (sport, Gamma tag, BetExplorer results page, BetExplorer moneyline type)
LEAGUES = {
    "nba": ("basketball", 745, "/basketball/usa/nba/results/", "ha"),
    "nfl": ("american football", 450, "/american-football/usa/nfl/results/", "ha"),
    "nhl": ("ice hockey", 899, "/hockey/usa/nhl/results/", "ha"),
    "epl": ("football", 82, "/football/england/premier-league/results/", "1x2"),
    "lal": ("football", 780, "/football/spain/laliga/results/", "1x2"),
    "bun": ("football", 1494, "/football/germany/bundesliga/results/", "1x2"),
    "sea": ("football", 101962, "/football/italy/serie-a/results/", "1x2"),
    "fl1": ("football", 102070, "/football/france/ligue-1/results/", "1x2"),
    "ucl": ("football", 100977, "/football/europe/champions-league/results/", "1x2"),
    "uel": ("football", 101787, "/football/europe/europa-league/results/", "1x2"),
}
GAME = re.compile(r"^([a-z0-9]+)-[a-z0-9]+-[a-z0-9]+-(\d{4}-\d{2}-\d{2})$")
STOP = {"fc", "cf", "afc", "sc", "ac", "club", "the", "cd", "ud", "de", "fk", "sk", "bc", "calcio", "ssc", "as"}


def _get(url, params=None, headers=None, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers={**HEADERS, **(headers or {})}, timeout=30)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 404):
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def be_get(path, ref=None, ajax=False):
    time.sleep(PAUSE)
    h = {"Referer": BE + ref} if ref else {}
    if ajax:
        h["X-Requested-With"] = "XMLHttpRequest"
    return _get(BE + path, headers=h)


# --- Polymarket -----------------------------------------------------------

def events(code: str, tag: int, days: int, now: pd.Timestamp) -> list[dict]:
    """The league's matches that started within `days`, with their markets."""
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
            if start.tzinfo is None:
                start = start.tz_localize("UTC")
            if start < now - pd.Timedelta(days=days):
                old += 1
                continue
            if not m or m[1] != code or e["slug"] in seen or start > now:
                continue
            seen.add(e["slug"])
            out.append({**e, "start": start})
        if old == len(rows):
            break
    for e in out:                                   # football keeps spreads and totals on a second event
        if LEAGUES[code][3] == "1x2":
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


def chosen(e: dict, code: str) -> list[dict]:
    """The markets worth a look: the moneyline(s), the busiest spread and total lines."""
    ms = [m for m in e.get("markets") or [] if len(_tokens(m)) == 2]
    vol = lambda m: float(m.get("volumeNum") or 0)  # noqa: E731
    out = []
    for kind in ("moneyline", "spreads", "totals"):
        group = sorted([m for m in ms if m.get("sportsMarketType") == kind and vol(m) >= MIN_VOLUME[kind]], key=vol, reverse=True)
        out += [{**m, "kind": kind} for m in (group if kind == "moneyline" else group[:LINES_PER_TYPE])]
    return out


def history(token: str, start: pd.Timestamp) -> pd.Series:
    r = _get(CLOB, {"market": token, "fidelity": 1, "startTs": int((start - pd.Timedelta(hours=36)).timestamp()),
                    "endTs": int(start.timestamp())})
    pts = (r.json() or {}).get("history", []) if r is not None else []
    return pd.Series({pd.Timestamp(int(x["t"]), unit="s", tz="UTC"): float(x["p"]) for x in pts}, dtype=float).sort_index()


def first_jumps(x: pd.Series, jump: float):
    d = (x - x.shift(freq=WINDOW).reindex(x.index)).dropna()
    out, last = [], None
    for t, v in d[d.abs() >= jump].items():
        if last is None or t - last > pd.Timedelta(hours=3):
            out.append((t, int(np.sign(v))))
            last = t
    return out


def crossing(s: pd.Series, t0, t1, sgn: int, least: float):
    pre, post = s[s.index <= t0], s[s.index <= t1]
    if pre.empty or post.empty or (post.iloc[-1] - pre.iloc[-1]) * sgn < least:
        return None
    mid, w = (pre.iloc[-1] + post.iloc[-1]) / 2, s[(s.index > t0) & (s.index <= t1)]
    hit = w[(w - mid) * sgn >= 0]
    return hit.index[0] if len(hit) else None


def level(s: pd.Series, t):
    s = s[s.index <= t]
    return float(s.iloc[-1]) if len(s) else np.nan


def moves(p: pd.Series, start: pd.Timestamp, jump: float) -> list[dict]:
    """Polymarket's big pre-match moves on one outcome's minute prices."""
    cut = start - pd.Timedelta(minutes=2)
    p = p[p.index < cut]
    if len(p) < 60:
        return []
    grid = pd.date_range(p.index[0].ceil("min"), cut.floor("min"), freq="min")
    P = p.reindex(p.index.union(grid)).ffill().reindex(grid)
    out = []
    for t, sgn in first_jumps(P, jump):
        t0, t1 = t - BEFORE, min(t + AFTER, cut)
        if t0 < grid[0] or t1 - t < WINDOW or (P[t1] - P[t0]) * sgn < jump:
            continue
        t_pm = crossing(P, t0, t1, sgn, jump / 2)
        if t_pm is not None:
            out.append({"t": t, "t0": t0, "t1": t1, "sgn": sgn, "t_pm": t_pm, "move": float((P[t1] - P[t0]) * sgn),
                        "close": float(P.iloc[-1]), "p_at": float(P[t_pm]), "cut": cut})
    return out


# --- BetExplorer ----------------------------------------------------------

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


def results(path: str) -> list[dict]:
    """A league's recent results: id, both names (home first), the day."""
    r = be_get(path)
    if r is None:
        return []
    out, today = [], pd.Timestamp.now(tz=CLOCK).normalize()
    for m in re.finditer(r'<a[^>]*href="([^"]+/([A-Za-z0-9]{8})/)"[^>]*class="in-match"[^>]*>(.*?)</a>(.*?)</tr>', r.text, re.S):
        names = [re.sub(r"<[^>]+>", "", x).strip() for x in m[3].split(" - ")]
        when = re.findall(r'h-text-no-wrap">([^<]+)<', m[4])
        if len(names) != 2 or not when:
            continue
        w = when[-1].strip()
        if w == "Today":
            day = today
        elif w == "Yesterday":
            day = today - pd.Timedelta(days=1)
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


def find_match(teams: list[str], start: pd.Timestamp, games: list[dict]):
    """The BetExplorer match of Polymarket's two teams on that day, and which of them is at home."""
    best = None
    day = start.tz_convert(CLOCK).normalize()
    for g in games:
        if abs((g["day"] - day).days) > 1:
            continue
        for flip in (False, True):
            a, b = (teams[1], teams[0]) if flip else (teams[0], teams[1])
            s1, s2 = _score(a, g["home"]), _score(b, g["away"])
            if min(s1, s2) >= 0.55 and (best is None or s1 + s2 > best[0]):
                best = (s1 + s2, g, flip)
    return (best[1], best[2]) if best else (None, None)


def _attrs(tag: str) -> dict:
    return dict(re.findall(r'([\w-]+)="([^"]*)"', tag))


def bet365_cells(match: dict, bt: str) -> dict:
    """bet365's cells of one bet type, by line ('' for a moneyline): the
    attributes of each outcome's cell, in the table's order."""
    r = be_get(f"/match-odds/{match['id']}/0/{bt}/odds/?lang=en", ref=match["url"], ajax=True)
    try:
        html = r.json().get("odds", "") if r is not None else ""
    except ValueError:
        html = ""
    blocks = re.findall(r'<tbody id="all-odds-([^"]*)"[^>]*>(.*?)</tbody>', html, re.S) or [("", html)]
    out = {}
    for line, body in blocks:
        for row in re.findall(r"<tr\s+data-bid=\"\d+\"[^>]*>.*?</tr>", body, re.S):
            if "bet365" not in row.lower():
                continue
            cells = [_attrs(c) for c in re.findall(r'<td([^>]*data-odd="[^"]*"[^>]*)>', row)]
            if cells:
                out[line] = cells
    return out


def _stamp(raw: str, year: int):
    d = re.match(r"(\d{2})\.(\d{2})\.\s*(\d{2}):(\d{2})", raw.strip())
    if not d:
        return None
    t = pd.Timestamp(year=year, month=int(d[2]), day=int(d[1]), hour=int(d[3]), minute=int(d[4]))
    return t.tz_localize(CLOCK, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def cell_history(cell: dict, match: dict, year: int) -> pd.Series:
    """One outcome's bet365 odds over time (UTC): the archive plus the current price."""
    path = "/archive-odds/{}/{}/{}/{}/{}/".format(*(cell.get(k, "") for k in ("data-oid", "data-bid", "data-bt", "data-sc", "data-hcp")))
    r = be_get(path, ref=match["url"], ajax=True)
    try:
        rows = r.json() if r is not None else []
    except ValueError:
        rows = []
    pts = {}
    for x in rows if isinstance(rows, list) else []:
        t = _stamp(x.get("date", ""), year)
        if t is not None:
            pts[t] = float(x["odd"])
    c = re.match(r"(\d+),(\d+),(\d+),(\d+),(\d+)", cell.get("data-created", ""))
    if c and cell.get("data-odd"):
        t = pd.Timestamp(year=int(c[3]), month=int(c[2]), day=int(c[1]), hour=int(c[4]), minute=int(c[5]))
        pts[t.tz_localize(CLOCK, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")] = float(cell["data-odd"])
    s = pd.Series(pts, dtype=float)
    return s[s.index.notna()].sort_index()


def fair_chances(series: list[pd.Series]) -> list[pd.Series]:
    """Each outcome's chance with bet365's margin taken out, at every change."""
    w = pd.concat(series, axis=1).sort_index().ffill().dropna()
    inv = 1 / w
    tot = inv.sum(axis=1)
    return [inv[i] / tot for i in range(len(series))]


# --- one match ------------------------------------------------------------

def _teams(e: dict) -> list[str]:
    parts = [x.strip() for x in re.split(r"\s+vs\.?\s+", e.get("title") or "", maxsplit=1)]
    return parts if len(parts) == 2 else []


def _side(m: dict, code: str, teams: list[str]):
    """Which outcome position of bet365's table each of the market's two
    outcomes is: (bet type, line, [pos of outcome 0, pos of outcome 1 or None])."""
    kind, q = m["kind"], m.get("question") or ""
    outs = json.loads(m.get("outcomes") or "[]")
    if kind == "moneyline" and LEAGUES[code][3] == "1x2":
        if re.search(r"\bdraw\b", q, re.I):
            return "1x2", "", ["X", None]
        name = re.sub(r"^Will\s+|\s+win.*$", "", q).strip()
        i = max(range(2), key=lambda k: _score(name, teams[k]))
        return "1x2", "", [str(i), None]                      # '0' or '1': which of the title's teams
    if kind == "moneyline":
        i = max(range(2), key=lambda k: _score(outs[0], teams[k]))
        return "ha", "", [str(i), str(1 - i)]
    line = m.get("line")
    if line is None:
        return None
    if kind == "totals":
        return "ou", float(line), ["over", "under"]
    i = max(range(2), key=lambda k: _score(outs[0], teams[k]))   # spreads: outcome 0 takes the line
    return "ah", float(line), [str(i), str(1 - i)]


def study_match(e: dict, code: str, games: list[dict], jump: float) -> list[dict]:
    teams = _teams(e)
    if not teams:
        return []
    found = []
    for m in chosen(e, code):
        tok = _tokens(m)
        p = history(tok[0], e["start"])
        mv = moves(p, e["start"], jump)
        if mv:
            found.append((m, mv))
        time.sleep(0.2)
    if not found:
        return []
    match, flip = find_match(teams, e["start"], games)
    if match is None:
        return [{"slug": e["slug"], "kind": m["kind"], "status": "no BetExplorer match", **{k: v for k, v in x.items() if k == "move"}}
                for m, mv in found for x in mv]
    year = e["start"].tz_convert(CLOCK).year
    tables, out = {}, []
    for m, mv in found:
        side = _side(m, code, teams)
        if side is None:
            continue
        bt, line, pos = side
        if bt not in tables:
            tables[bt] = bet365_cells(match, bt)
        cells = tables[bt]
        home = lambda i: (int(i) == 0) != flip                  # noqa: E731  title team i is BetExplorer's home side
        if bt in ("ha", "1x2"):
            row = cells.get("") or (next(iter(cells.values())) if len(cells) == 1 else None)
            if row is None:
                out += [{"slug": e["slug"], "kind": m["kind"], "status": "no bet365 price", "move": x["move"]} for x in mv]
                continue
            order = {"1": 0, "X": 1, "2": 2} if bt == "1x2" else {"1": 0, "2": 1}
            def col(i):
                if i == "X":
                    return order["X"]
                return order["1"] if home(i) else order["2"]
            hist = [cell_history(c, match, year) for c in row]
            idx = [col(pos[0]), col(pos[1]) if pos[1] is not None else None]
        else:
            want = line if bt == "ou" else None
            key = None
            for k in cells:
                try:
                    v = float(k)
                except ValueError:
                    continue
                if bt == "ou" and abs(v - want) < 1e-6:
                    key = k
                if bt == "ah":
                    # the table's handicap is the home side's: outcome 0 takes `line`
                    target = line if home(pos[0]) else -line
                    if abs(v - target) < 1e-6:
                        key = k
            if key is None or len(cells[key]) < 2:
                out += [{"slug": e["slug"], "kind": m["kind"], "status": "line not at bet365", "move": x["move"]} for x in mv]
                continue
            row = cells[key]
            hist = [cell_history(c, match, year) for c in row[:2]]
            if bt == "ou":
                idx = [0, 1]
            else:
                idx = [0, 1] if home(pos[0]) else [1, 0]
        if any(h.empty for h in hist):
            out += [{"slug": e["slug"], "kind": m["kind"], "status": "no bet365 history", "move": x["move"]} for x in mv]
            continue
        fair = fair_chances(hist)
        for x in mv:
            rising = idx[0] if x["sgn"] > 0 else idx[1]
            if rising is None:                                  # a football win market that fell: no single bet365 side
                continue
            q = fair[rising]
            odds = hist[rising]
            at = x["t_pm"] + pd.Timedelta(minutes=1)
            o_stale, o_before, o_close = level(odds, at), level(odds, x["t0"]), level(odds, x["cut"])
            fair_close = x["close"] if x["sgn"] > 0 else 1 - x["close"]
            if bt == "1x2" and x["sgn"] < 0:
                continue
            t_b = crossing(q, x["t0"], x["t1"], 1, x["move"] / 3)
            pm_side = x["p_at"] if x["sgn"] > 0 else 1 - x["p_at"]
            gap = abs(level(q, x["t_pm"]) - pm_side)            # a wrong side or line shows as a wide gap
            out.append({"slug": e["slug"], "league": code, "kind": m["kind"], "status": "ok",
                        "question": m.get("question"), "move": round(x["move"], 4), "t_pm": x["t_pm"].isoformat(),
                        "lag_min": round((t_b - x["t_pm"]).total_seconds() / 60, 1) if t_b is not None else None,
                        "followed": t_b is not None, "unchanged_at_1min": bool(o_stale == o_before),
                        "odds_before": o_before, "odds_stale": o_stale, "odds_close": o_close,
                        "fair_close": round(fair_close, 4),
                        "value": round(fair_close * o_stale - 1, 4) if not np.isnan(o_stale) else None,
                        "clv_vs_bet365_close": round(o_stale / o_close - 1, 4) if o_close and not np.isnan(o_stale) else None,
                        "chance_gap": round(gap, 4) if not np.isnan(gap) else None})
    return out


MAX_GAP = 0.15                  # bet365's chance this far from Polymarket's: a mapping error, not a price


def summary(rows: list[dict]) -> dict:
    for r in rows:
        if r.get("status") == "ok" and r.get("chance_gap") is None:
            r["status"] = "no bet365 price yet at the move"
        elif r.get("status") == "ok" and r["chance_gap"] > MAX_GAP:
            r["status"] = "bet365 chance too far from Polymarket's"
    ok = [r for r in rows if r.get("status") == "ok" and r.get("value") is not None]
    if not ok:
        return {"moves": len(rows), "with_bet365": 0}
    v = np.array([r["value"] for r in ok])
    lags = np.array([r["lag_min"] for r in ok if r["lag_min"] is not None])
    return {"moves": len(rows), "with_bet365": len(ok),
            "bet365_followed": round(float(np.mean([r["followed"] for r in ok])), 3),
            "lag_median_min": round(float(np.median(lags)), 1) if len(lags) else None,
            "lag_over_5_min": round(float(np.mean(lags > 5)), 3) if len(lags) else None,
            "unchanged_a_minute_after": round(float(np.mean([r["unchanged_at_1min"] for r in ok])), 3),
            "value_mean": round(float(v.mean()), 4), "value_median": round(float(np.median(v)), 4),
            "value_positive": round(float(np.mean(v > 0)), 3), "value_over_2pct": round(float(np.mean(v > 0.02)), 3),
            "skipped": {s: sum(1 for r in rows if r.get("status") == s) for s in
                        {r.get("status") for r in rows} - {"ok"}}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=6)
    ap.add_argument("--jump", type=float, default=0.03)
    ap.add_argument("--leagues", default=",".join(LEAGUES))
    args = ap.parse_args()
    now = pd.Timestamp.now(tz="UTC")
    rows, matches = [], {}
    for code in args.leagues.split(","):
        sport, tag, path, _ = LEAGUES[code]
        evs = events(code, tag, args.days, now)
        games = results(path)
        matches[code] = len(evs)
        print(f"{code}: {len(evs)} Polymarket matches, {len(games)} BetExplorer results", flush=True)
        for e in evs:
            try:
                rows += study_match(e, code, games, args.jump)
            except Exception as exc:                            # one odd match must not end the study
                print("  skipped", e.get("slug"), exc, flush=True)
    by = {}
    for r in rows:
        sport = LEAGUES[r.get("league") or r["slug"].split("-")[0]][0]
        by.setdefault(sport, {}).setdefault(r["kind"], []).append(r)
    report = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "days": args.days,
              "jump": args.jump, "bookmaker": "bet365.us (BetExplorer from a US address)", "matches": matches,
              "by_sport": {s: {k: summary(v) for k, v in kinds.items()} for s, kinds in by.items()},
              "all": summary(rows), "moves": rows}
    OUT.write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: report[k] for k in ("matches", "by_sport", "all")}, indent=1, default=str))


if __name__ == "__main__":
    main()
