"""tennisratio.com: per-match pressure-point counts.

What this adds that nothing else we have does: the score states. Every
other source gives aggregate serve and return counts for a match; this
one breaks them down by the situation the point was played in --
0:30, 0:40, 15:30, 15:40, 30:30, 30:40, 40:40, 40:A -- separately for
serving and returning, with both a numerator and a denominator.

That matters because "clutch" measured through break points alone is
badly under-sampled: roughly half a break point per service game against
1.6 (ATP) to 2.3 (WTA) pressure points. Our own split-half test put the
reliability of break-point clutch at +0.064, and the obvious objection
was that the sample is too thin to see a real effect. This source is the
data needed to answer that objection properly.

robots.txt (checked 2026-09) disallows /admin/, /articles/tag/, /api/
and any URL with ?q= or ?page=. The player pages used here are not
disallowed, and the match data is embedded in their HTML rather than
fetched from the API -- so nothing here touches a disallowed path. The
pages are large (>1 MB), so requests are cached on disk and paced.
"""
from __future__ import annotations

import json
import logging
import re
import time

import pandas as pd
import requests

from tennissharp import config

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tennisratio.com"
PLAYER_SITEMAP = f"{BASE_URL}/sitemap-players.xml"
# A browser string: the site refuses the default python-requests agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TennisSharpBot research script; "
                          "+https://github.com/karlewaczko/TennisSharpBot)"}
REQUEST_PAUSE = 1.5     # seconds between fetches; the pages are over a megabyte

SCORE_STATES = ("0_30", "0_40", "15_30", "15_40", "30_30", "30_40", "40_40", "40_A")


def player_urls(cache_only: bool = False) -> list[str]:
    path = config.RAW_DIR / "tennisratio" / "sitemap-players.xml"
    if not path.exists() and not cache_only:
        path.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(PLAYER_SITEMAP, headers=_HEADERS, timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    if not path.exists():
        return []
    return re.findall(r"<loc>([^<]+)</loc>", path.read_text(encoding="utf-8", errors="ignore"))


def slug_from_url(url: str) -> str:
    return url.rsplit("/", 1)[-1].removesuffix(".html")


def fetch_player_html(url: str, force: bool = False) -> str | None:
    """Cached page fetch. Returns None when the page cannot be retrieved."""
    dest = config.RAW_DIR / "tennisratio" / f"{slug_from_url(url)}.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size and not force:
        return dest.read_text(encoding="utf-8", errors="ignore")
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=90)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("tennisratio: %s (%s)", url, exc)
        return None
    dest.write_text(resp.text, encoding="utf-8")
    time.sleep(REQUEST_PAUSE)
    return resp.text


def extract_matches(html: str) -> list[dict]:
    """The match array embedded in a player page.

    It is a bare JSON array in the page source rather than a labelled
    <script type="application/json">, so it is located by one of its own
    keys and then bracket-matched -- a non-greedy regex would stop at the
    first nested brace.
    """
    anchor = html.find('"serve_pressure_all"')
    if anchor == -1:
        return []
    start = html.rfind("[{", 0, anchor)
    if start == -1:
        return []
    depth = 0
    for i in range(start, len(html)):
        if html[i] == "[":
            depth += 1
        elif html[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:i + 1])
                except ValueError:
                    return []
    return []


def load_players(urls=None, limit: int | None = None) -> pd.DataFrame:
    """One row per player-match across the requested player pages."""
    urls = list(urls or player_urls())
    if limit:
        urls = urls[:limit]
    frames = []
    for url in urls:
        html = fetch_player_html(url)
        if not html:
            continue
        rows = extract_matches(html)
        if not rows:
            continue
        df = pd.DataFrame(rows)
        df["player_slug"] = slug_from_url(url)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out.dropna(subset=["date"])


def pressure_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Pressure-point win rates with their denominators kept.

    `serve_pressure_rate` is the share of points won while serving in a
    state where the game is at immediate risk; `serve_baseline` is the
    same player's overall share of service points won in that match. The
    difference between them is the quantity every "clutch" claim rests
    on, and keeping `serve_pressure_all` alongside it is what makes the
    difference measurable rather than merely computable.
    """
    out = df.copy()
    for side in ("serve", "return"):
        allp = out[f"{side}_pressure_all"]
        out[f"{side}_pressure_rate"] = (out[f"{side}_pressure_won"] / allp).where(allp > 0)
    svpt = out["first_serve_points"] + out["second_serve_points"]
    rtpt = out["return_1st_serve_points"] + out["return_2nd_serve_points"]
    out["serve_points"] = svpt
    out["return_points"] = rtpt
    return out
