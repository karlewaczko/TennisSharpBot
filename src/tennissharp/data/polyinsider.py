"""PolyInsider (polyinsider.io): an independent Polymarket analytics site.

It reads Polymarket's public trade stream and data API and publishes, per
trader, a tracked P&L, volume and win rate (share of settled markets that
finished in profit), plus whale bets ($5,000+) and fresh-wallet bets
(first trade under 24 hours ago, one market only, $500+) per market.

Used here as a second, independent look at a wallet: its trader page
embeds the statistics per period in the page payload. robots.txt allows
the pages and disallows /api/ and /api-proxy/; only pages are read, one
every few seconds, under a user agent that names this project. Its
methodology page invites quoting and linking."""
from __future__ import annotations

import json
import logging
import re
import time

import requests

BASE = "https://polyinsider.io"
USER_AGENT = "TennisSharpBot/1.0 (+https://github.com/karlewaczko/TennisSharpBot)"
PAUSE = 2.0

log = logging.getLogger(__name__)
_MONEY = re.compile(r"^([+\-−]?)\$([\d.,]+)([KMB]?)$")
_TITLE = re.compile(r"Polymarket:\s*([+\-−]?\$[\d.,]+[KMB]?)\s*P&(?:amp;)?L,\s*(\$[\d.,]+[KMB]?)\s*Volume")
_STATS = ("winRate", "closedPredictions", "winningPredictions", "losingPredictions", "predictionCount",
          "totalVolume", "totalTrades", "biggestWin")


def trader_url(wallet: str) -> str:
    return f"{BASE}/en/trader/{wallet}"


def market_url(slug: str) -> str:
    """PolyInsider's page for a market: its whale and fresh-wallet bets.
    The slug is Polymarket's event slug."""
    return f"{BASE}/en/markets/{slug}"


def money(text: str) -> float | None:
    """'+$1.3M' -> 1300000.0, '-$99.5K' -> -99500.0, '$850' -> 850.0"""
    m = _MONEY.match(str(text).strip())
    if not m:
        return None
    value = float(m.group(2).replace(",", "")) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(3)]
    return -value if m.group(1) in ("-", "−") else value


def _payload(page: str) -> str:
    """The page's React server payload, the chunks pushed to self.__next_f."""
    out = []
    for chunk in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page, re.S):
        try:
            out.append(json.loads('"' + chunk + '"'))
        except ValueError:
            continue
    return "".join(out)


def _object_at(text: str, start: int) -> dict | None:
    depth = 0
    for end in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[end], 0)
        if depth == 0:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                return None
    return None


def parse_trader(page: str) -> dict | None:
    """All-time tracked P&L and volume (from the title, as the page shows
    them) and the win-rate statistics for all time and the last month."""
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    head = _TITLE.search(title.group(1)) if title else None
    if not head:
        return None
    out = {"pnl": money(head.group(1)), "volume": money(head.group(2))}
    payload = _payload(page)
    for m in re.finditer(r'"winRate":', payload):
        start = payload.rfind('{"range":"', 0, m.start())
        stats = _object_at(payload, start) if start >= 0 else None
        if not stats or stats.get("range") not in ("all", "1m"):
            continue
        suffix = "" if stats["range"] == "all" else "_1m"
        for key in _STATS:
            if stats.get(key) is not None:
                out[f"{key}{suffix}"] = stats[key]
    return out


def trader(wallet: str, http=requests, sleep=time.sleep) -> dict | None:
    """One wallet's PolyInsider figures, or None when the page cannot be
    read or parsed (a missing second opinion is not a verdict)."""
    try:
        r = http.get(trader_url(wallet), headers={"User-Agent": USER_AGENT}, timeout=30)
        sleep(PAUSE)
        if r.status_code != 200:
            log.warning("PolyInsider %s: HTTP %s", wallet, r.status_code)
            return None
        return parse_trader(r.text)
    except requests.RequestException as exc:
        log.warning("PolyInsider %s: %s", wallet, exc)
        return None
