#!/usr/bin/env python3
"""Watch NBA moneylines at Polymarket and Kalshi and post sharp pre-match
jumps to Telegram and/or Discord.

    python scripts/sharp_move_alert.py --minutes 345
    python scripts/sharp_move_alert.py --test        # one test message, then stop

Every --poll seconds: Polymarket's midpoints (CLOB) and Kalshi's bid and ask
(public API) for every NBA game starting within 36 hours. A side rising 3+
points within half an hour before the start (tennissharp.sharp_moves) is
posted with the lowest bet365 price still worth taking. Where it goes:
Telegram when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set, Discord when
DISCORD_WEBHOOK_URL is; without either the alert is only printed and logged.
Every alert is appended to data/processed/sharp_move_alerts.csv, so the test
can be reckoned up against the closing prices later.

.github/workflows/sharp-moves.yml runs it every evening for the hours before
the NBA tips off. Kalshi refuses requests from a browser, so this cannot
live in docs/profis.html; the radar there shows Polymarket's jumps only.
"""
import _bootstrap  # noqa: F401
import argparse
import csv
import datetime as dt
import os
import re
import time
from zoneinfo import ZoneInfo

import requests

from tennissharp import config
from tennissharp import sharp_moves as sm

GAMMA, CLOB = "https://gamma-api.polymarket.com", "https://clob.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script)"}
LOCAL = ZoneInfo("Europe/Vienna")
LOG = config.PROCESSED_DIR / "sharp_move_alerts.csv"
LOG_COLUMNS = ["alerted_at", "league", "game", "team", "venue", "before", "now", "others", "fair", "min_odds",
               "start", "sent"]
LEAGUES = {"nba": {"label": "🏀 NBA", "tag": 745, "kalshi": "KXNBAGAME"}}
AHEAD_H = 36                 # games starting within this many hours are watched
REFRESH_S = 600              # the list of games is read again this often
SLUG = re.compile(r"^([a-z]+)-([a-z0-9]+)-([a-z0-9]+)-(\d{4}-\d{2}-\d{2})$")
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def _get(url, params=None, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 * (i + 1))
    return None


def _start(raw) -> float | None:
    """Gamma's gameStartTime ('2026-11-12 00:00:00+00') in seconds."""
    s = str(raw or "").strip().replace(" ", "T")
    s = re.sub(r"([+-]\d\d)$", r"\1:00", s)
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).timestamp()


def _json(raw):
    import json
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or [])
    except ValueError:
        return []


def polymarket_games(code: str, now: float) -> dict:
    """Polymarket's open moneylines of a league starting within AHEAD_H, by (date, team codes)."""
    out = {}
    lo = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    for off in range(0, 1000, 100):
        rows = _get(f"{GAMMA}/markets", {"tag_id": LEAGUES[code]["tag"], "closed": "false", "sports_market_types": "moneyline",
                                         "limit": 100, "offset": off, "end_date_min": lo.isoformat(),
                                         "end_date_max": (lo + dt.timedelta(days=4)).isoformat()})
        if not isinstance(rows, list) or not rows:
            break
        for m in rows:
            ev = (m.get("events") or [{}])[0]
            g = SLUG.match(ev.get("slug") or m.get("slug") or "")
            start, outcomes, tokens = _start(m.get("gameStartTime")), _json(m.get("outcomes")), _json(m.get("clobTokenIds"))
            if not g or g[1] != code or start is None or not now < start <= now + AHEAD_H * 3600 \
                    or len(outcomes) != 2 or len(tokens) != 2:
                continue
            codes = [g[2].upper(), g[3].upper()]
            out[(g[4], frozenset(codes))] = {"slug": g[0], "title": ev.get("title") or m.get("question"), "start": start,
                                             "teams": dict(zip(codes, outcomes)), "codes": codes, "token": tokens[0]}
        if len(rows) < 100:
            break
    return out


def _kalshi_date(tail: str) -> str | None:
    d = re.match(r"(\d{2})([A-Z]{3})(\d{2})", tail)
    if not d or d[2] not in MONTHS:
        return None
    return f"20{d[1]}-{MONTHS[d[2]]:02d}-{d[3]}"


def kalshi_games(code: str) -> dict:
    """Kalshi's open game markets of a league, by (date, team codes): each team's market and mid price."""
    out, cursor = {}, None
    for _ in range(10):
        params = {"series_ticker": LEAGUES[code]["kalshi"], "status": "open", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        js = _get(f"{KALSHI}/markets", params) or {}
        for m in js.get("markets", []):
            tail = str(m.get("event_ticker", "")).split("-", 1)[-1]          # 26NOV11OKCPOR
            date, team = _kalshi_date(tail), str(m.get("ticker", "")).rsplit("-", 1)[-1]
            codes = re.sub(r"^\d{2}[A-Z]{3}\d{2}", "", tail)
            if not date or len(codes) != 6:
                continue
            g = out.setdefault((date, frozenset([codes[:3], codes[3:]])),
                               {"teams": {}, "mid": {}, "tickers": {}, "event": m.get("event_ticker"), "end": None})
            g["teams"][team] = str(m.get("yes_sub_title") or team)
            g["tickers"][team] = m.get("ticker")
            g["end"] = _start(m.get("expected_expiration_time")) or g["end"]
            bid, ask = _num(m.get("yes_bid_dollars")), _num(m.get("yes_ask_dollars"))
            if bid is not None and ask is not None and 0 < bid <= ask < 1 and ask - bid <= 0.10:
                g["mid"][team] = (bid + ask) / 2
        cursor = js.get("cursor")
        if not cursor:
            break
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def polymarket_mids(tokens: list[str]) -> dict:
    """Outcome 0's midpoint of each market, in one request where the CLOB takes it."""
    if not tokens:
        return {}
    try:
        r = requests.post(f"{CLOB}/midpoints", json=[{"token_id": t} for t in tokens], headers=HEADERS, timeout=20)
        if r.status_code == 200 and isinstance(r.json(), dict):
            return {t: _num(v) for t, v in r.json().items() if _num(v) is not None}
    except (requests.RequestException, ValueError):
        pass
    out = {}
    for t in tokens:
        js = _get(f"{CLOB}/midpoint", {"token_id": t}, tries=1) or {}
        if _num(js.get("mid")) is not None:
            out[t] = _num(js["mid"])
    return out


def seed_polymarket(token: str, now: float) -> list[tuple[float, float]]:
    js = _get(f"{CLOB}/prices-history", {"market": token, "startTs": int(now - 2400), "endTs": int(now), "fidelity": 1}) or {}
    return [(float(x["t"]), float(x["p"])) for x in js.get("history", []) if "t" in x and "p" in x]


def seed_kalshi(series: str, ticker: str, now: float) -> list[tuple[float, float]]:
    js = _get(f"{KALSHI}/series/{series}/markets/{ticker}/candlesticks",
              {"start_ts": int(now - 2400), "end_ts": int(now), "period_interval": 1}) or {}
    out = []
    for c in js.get("candlesticks", []):
        bid, ask = _num((c.get("yes_bid") or {}).get("close_dollars")), _num((c.get("yes_ask") or {}).get("close_dollars"))
        if bid is not None and ask is not None and 0 < bid <= ask < 1 and ask - bid <= 0.10:
            out.append((float(c["end_period_ts"]), (bid + ask) / 2))
    return out


def send(text: str) -> str:
    """Post to whichever channels are set up; the tokens are never printed."""
    sent = []
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if tok and chat:
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=20)
            sent.append("telegram" if r.ok else f"telegram failed ({r.status_code})")
        except requests.RequestException as exc:
            sent.append(f"telegram failed ({type(exc).__name__})")
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if hook:
        try:
            r = requests.post(hook, json={"content": text}, timeout=20)
            sent.append("discord" if r.status_code in (200, 204) else f"discord failed ({r.status_code})")
        except requests.RequestException as exc:
            sent.append(f"discord failed ({type(exc).__name__})")
    if not sent:
        print(text, flush=True)
    return ",".join(sent) or "printed"


def log(row: dict) -> None:
    new = not LOG.exists()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k) for k in LOG_COLUMNS})


def local(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, LOCAL).strftime("%d.%m. %H:%M")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=345, help="how long to watch")
    ap.add_argument("--poll", type=float, default=20, help="seconds between price checks")
    ap.add_argument("--leagues", default="nba")
    ap.add_argument("--test", action="store_true", help="send one test message and stop")
    args = ap.parse_args()
    if args.test:
        print("test message:", send("Testnachricht vom Kurssprung-Alarm (TennisSharpBot). Der Kanal ist eingerichtet."))
        return
    watch, deadline = sm.Watch(), time.time() + args.minutes * 60
    games, kal, listed, flips = {}, {}, 0.0, {}
    print(f"watching {args.leagues} until {local(deadline)} (Vienna)", flush=True)
    while time.time() < deadline:
        now = time.time()
        for code in args.leagues.split(","):
            if now - listed > REFRESH_S:
                games[code] = polymarket_games(code, now)
            kal[code] = kalshi_games(code)
        if now - listed > REFRESH_S:
            listed = now
            print(f"{local(now)}: " + ", ".join(f"{c} {len(games[c])} Polymarket / {len(kal[c])} Kalshi games" for c in games), flush=True)
        for code in args.leagues.split(","):
            pm, ks = games.get(code, {}), kal.get(code, {})
            mids = polymarket_mids([g["token"] for g in pm.values()])
            for key in set(pm) | set(ks):
                g, k = pm.get(key), ks.get(key)
                start = g["start"] if g else ((k or {}).get("end") or 0) - 2.5 * 3600
                if not start or now >= start - 120 or start > now + AHEAD_H * 3600:
                    continue
                codes = g["codes"] if g else sorted(key[1])
                teams = {c: (g["teams"].get(c) if g else None) or ((k or {}).get("teams") or {}).get(c) or c for c in codes}
                prices = {}                                   # venue -> team code -> chance now
                if g and g["token"] in mids:
                    p0 = mids[g["token"]]
                    prices["Polymarket"] = {codes[0]: p0, codes[1]: 1 - p0}
                if k and k["mid"]:
                    prices["Kalshi"] = dict(k["mid"])
                # Polymarket's outcome 0 is taken as the slug's first team; Kalshi's prices check that once
                if key not in flips and "Polymarket" in prices and len(prices.get("Kalshi", {})) == 2:
                    a, b = codes
                    flips[key] = (abs(prices["Polymarket"][a] - prices["Kalshi"][a]) > 0.25
                                  and abs(prices["Polymarket"][a] - prices["Kalshi"][b]) < 0.1)
                pm_flip = flips.get(key, False)
                if pm_flip and "Polymarket" in prices:
                    a, b = codes
                    prices["Polymarket"] = {a: prices["Polymarket"][b], b: prices["Polymarket"][a]}
                for venue, by_team in prices.items():
                    for team, p in by_team.items():
                        vkey, side = f"{venue}|{key[0]}|{team}", f"{key[0]}|{'-'.join(sorted(key[1]))}|{team}"
                        if not watch.seen(vkey):                       # half an hour of history first, alerts held back
                            if venue == "Polymarket":
                                first = (team == codes[0]) != pm_flip
                                pts = [(t, q if first else 1 - q) for t, q in seed_polymarket(g["token"], now)]
                            else:
                                pts = seed_kalshi(LEAGUES[code]["kalshi"], k["tickers"].get(team) or "", now)
                            for t, q in sorted(pts):
                                watch.update(vkey, side, t, q)
                        move = watch.update(vkey, side, now, p)
                        if not move:
                            continue
                        others = {v: bt[team] for v, bt in prices.items() if v != venue and team in bt}
                        title = " – ".join(teams[c] for c in codes)
                        text, fair, least = sm.alert_text(LEAGUES[code]["label"], title, local(start), teams[team], venue,
                                                          move["before"], move["now"], others,
                                                          f"https://polymarket.com/event/{g['slug']}" if g else None)
                        sent = send(text)
                        log({"alerted_at": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds"),
                             "league": code, "game": g["slug"] if g else f"kalshi {k.get('event')}", "team": teams[team],
                             "venue": venue, "before": round(move["before"], 4), "now": round(move["now"], 4),
                             "others": ";".join(f"{v}={q:.4f}" for v, q in others.items()), "fair": round(fair, 4),
                             "min_odds": least, "start": dt.datetime.fromtimestamp(start, dt.timezone.utc).isoformat(timespec="minutes"),
                             "sent": sent})
                        print(f"{local(now)} alert {teams[team]} ({venue} {move['before']:.2f} -> {move['now']:.2f}): {sent}", flush=True)
        time.sleep(max(1.0, args.poll - (time.time() - now)))
    print("done", flush=True)


if __name__ == "__main__":
    main()
