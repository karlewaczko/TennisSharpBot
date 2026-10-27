"""Write docs/profis.html, the live page of what Polymarket's best-ranked
tennis, football and basketball wallets are betting right now.

The page reads Polymarket from the viewer's browser every 90 seconds (both
public APIs answer any origin); this script only embeds whom to watch: the
top of each sport's ranking from scripts/update_pm_traders.py, and which
sport each league code at the start of an event slug belongs to. GitHub
Pages serves the docs folder of main."""
from __future__ import annotations

import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import json
from pathlib import Path

import pandas as pd
import requests

from tennissharp import config
from tennissharp.data import polymarket_traders as pt

SPORTS = {"tennis": "Tennis", "soccer": "Fußball", "basketball": "Basketball"}
TOP_N = 12
TEMPLATE = Path(__file__).parent / "templates" / "profis.html"
OUT = config.REPO_ROOT / "docs" / "profis.html"
PLACEHOLDER = "__PROS_DATA__"
# Used when Gamma's /sports cannot be read: the leagues that carry the money.
FALLBACK_PREFIXES = {
    **{c: "tennis" for c in ("atp", "wta", "itf")},
    **{c: "soccer" for c in ("epl", "lal", "bun", "sea", "fl1", "ucl", "uel", "mls", "ere", "por", "elc")},
    **{c: "basketball" for c in ("nba", "wnba", "ncaab", "cbb", "euroleague")},
}


def sport_prefixes(http=requests) -> dict:
    """League code (the first part of an event slug) -> sport, from the
    tags Gamma lists for each league."""
    out = dict(FALLBACK_PREFIXES)
    try:
        rows = http.get(f"{pt.GAMMA_API}/sports", timeout=30).json()
    except (requests.RequestException, ValueError):
        return out
    for r in rows if isinstance(rows, list) else []:
        code = str(r.get("sport") or "").strip()
        tags = {int(t) for t in str(r.get("tags") or "").split(",") if t.strip().isdigit()}
        for sport, sport_tags in pt.SPORT_TAGS.items():
            if code and tags & set(sport_tags):
                out[code] = sport
                break
    return out


def _report(sport: str) -> dict:
    name = "prediction_market_sharpness.json" if sport == "tennis" else f"pm_{sport}_traders.json"
    try:
        return json.loads((config.REPORTS_DIR / name).read_text())
    except (OSError, ValueError):
        return {}


def collect(top_n: int = TOP_N) -> dict:
    """The watched wallets, once each, with their rank in every sport they
    are ranked in."""
    sports, wallets = {}, {}
    for sport, label in SPORTS.items():
        try:
            lb = pd.read_csv(config.PROCESSED_DIR / f"pm_{sport}_traders.csv")
        except (OSError, ValueError):
            continue
        if lb.empty:
            continue
        rep = _report(sport)
        sports[sport] = {"label": label, "measured_at": rep.get("measured_at"),
                         "window_days": rep.get("window_days"), "ranked": int(len(lb))}
        for r in lb.head(top_n).itertuples(index=False):
            w = wallets.setdefault(r.wallet, {"wallet": r.wallet, "name": "", "ranks": {}})
            if isinstance(r.name, str) and r.name and not w["name"]:
                w["name"] = r.name
            w["ranks"][sport] = {"rank": int(r.rank), "clv": round(float(r.clv_mean), 4),
                                 "t": round(float(r.clv_t), 2), "matches": int(r.pre_markets),
                                 "stake": round(float(r.stake)), "pnl": round(float(r.pnl))}
    return {"sports": sports, "wallets": list(wallets.values()), "top_n": top_n}


def render(data: dict, template: str) -> str:
    assert template.count(PLACEHOLDER) == 1, "template must hold the data placeholder once"
    # Inside <script>, "</" would end the block early: a profile name can hold anything.
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(PLACEHOLDER, blob)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=TOP_N, help="wallets watched per sport")
    ap.add_argument("-o", "--out", type=Path, default=OUT)
    args = ap.parse_args()
    data = collect(args.top)
    data["prefixes"] = sport_prefixes()
    data["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(data, TEMPLATE.read_text()))
    ranked = ", ".join(f"{sport} {info['ranked']}" for sport, info in data["sports"].items())
    print(f"{args.out}: {len(data['wallets'])} wallets watched ({ranked} ranked), "
          f"{len(data['prefixes'])} league codes")


if __name__ == "__main__":
    main()
