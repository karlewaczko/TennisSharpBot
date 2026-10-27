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
from tennissharp.data import polyinsider, polymarket_traders as pt

SPORTS = {"tennis": "Tennis", "soccer": "Fußball", "basketball": "Basketball"}
TOP_N = 12
TEMPLATE = Path(__file__).parent / "templates" / "profis.html"
OUT = config.REPO_ROOT / "docs" / "profis.html"
PLACEHOLDER = "__PROS_DATA__"
STATS_DIR = config.RAW_DIR / "pm"            # every wallet's figures, from update_pm_traders.py
WATCHED = config.PROCESSED_DIR / "pm_watched_clv.csv"
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


def _table(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
    except (OSError, ValueError):
        return None
    return None if df.empty else df.drop_duplicates("wallet").set_index("wallet")


FIGURES = ["rank", "clv", "gross", "t", "matches", "stake", "pnl", "fees", "taker", "sig", "elite"]


def _num(r, col, digits=None):
    v = r[col] if col in r.index else None
    if v is None or pd.isna(v):
        return None
    return round(float(v), digits) if digits is not None else round(float(v))


def _figures(r, rank) -> dict:
    """A wallet's 30-day figures in one sport: CLV after fees (`clv`; the
    gross figure where a table predates fees), before fees (`gross`)."""
    net = _num(r, "clv_net_mean", 4)
    t = _num(r, "clv_net_t", 2) if net is not None else _num(r, "clv_t", 2)
    sig = r["significant"] if "significant" in r.index and pd.notna(r["significant"]) else None
    elite = r["elite"] if "elite" in r.index and pd.notna(r["elite"]) else None
    return {"rank": rank, "clv": net if net is not None else _num(r, "clv_mean", 4), "gross": _num(r, "clv_mean", 4),
            "t": t, "matches": int(r["pre_markets"]), "stake": _num(r, "stake"), "pnl": _num(r, "pnl"),
            "fees": _num(r, "fees"), "taker": _num(r, "taker_share", 3), "sig": bool(sig) if sig is not None else None,
            "elite": bool(elite) if elite is not None else None}


def _previous() -> dict:
    """The figures the last build embedded, for a rebuild without this
    run's per-wallet tables (they live under data/raw)."""
    try:
        df = pd.read_csv(WATCHED)
    except (OSError, ValueError):
        return {}
    out = {}
    for _, r in df.iterrows():
        fig = {k: (None if k not in r.index or pd.isna(r[k]) else r[k]) for k in FIGURES}
        for k in ("rank", "matches", "stake", "pnl", "fees"):
            fig[k] = int(fig[k]) if fig[k] is not None else None
        for k in ("sig", "elite"):
            fig[k] = bool(fig[k]) if fig.get(k) is not None else None
        out[(r["wallet"], r["sport"])] = fig
    return out


def second_opinion(wallets: list[dict], fetch=None) -> None:
    """Each watched account as PolyInsider sees it: tracked P&L and volume
    over all time, win rate over all settled markets and the last month."""
    fetch = fetch or polyinsider.trader
    for w in wallets:
        figures = fetch(w["wallet"])
        if not figures:
            continue
        w["pi"] = {"pnl": figures.get("pnl"), "volume": figures.get("volume"),
                   "win_rate": figures.get("winRate"), "closed": figures.get("closedPredictions"),
                   "won": figures.get("winningPredictions"), "win_rate_1m": figures.get("winRate_1m"),
                   "closed_1m": figures.get("closedPredictions_1m")}


def alltime(wallets: list[dict], http=requests) -> None:
    """Each watched account's all-time profit and volume on Polymarket, as
    its profile page shows them, fetched fresh for the page."""
    for w in wallets:
        figures = pt.alltime(w["wallet"], http, sleep=lambda s: None)
        if figures:
            w["alltime"] = {"pnl": round(figures[0]), "vol": round(figures[1])}


def collect(top_n: int = TOP_N) -> dict:
    """The watched wallets (the top of each sport's ranking), once each, with
    their closing-line value in every sport they have enough matches in:
    from the ranking where they are ranked, else from the run's table of
    all wallets."""
    sports, wallets, boards, stats = {}, {}, {}, {}
    for sport, label in SPORTS.items():
        lb = _table(config.PROCESSED_DIR / f"pm_{sport}_traders.csv")
        if lb is None:
            continue
        boards[sport] = lb
        table = _table(STATS_DIR / f"pm_{sport}_wallet_stats.csv")
        if table is not None:
            stats[sport] = table
        rep = _report(sport)
        # Only the very best are watched: the wallets that meet every
        # criterion (pt.mark_elite), or at least an edge beyond luck in an
        # older ranking.
        flag = "elite" if "elite" in lb.columns else "significant" if "significant" in lb.columns else None
        watch = lb[lb[flag].fillna(False).astype(bool)] if flag else lb
        sports[sport] = {"label": label, "measured_at": rep.get("measured_at"),
                         "window_days": rep.get("window_days"), "ranked": int(len(lb)),
                         "significant": int(lb["significant"].fillna(False).astype(bool).sum())
                         if "significant" in lb.columns else int(len(lb)),
                         "elite": int(len(watch))}
        for wallet, r in watch.head(top_n).iterrows():
            w = wallets.setdefault(wallet, {"wallet": wallet, "name": "", "ranks": {}, "clv": {}})
            if isinstance(r["name"], str) and r["name"] and not w["name"]:
                w["name"] = r["name"]
            w["ranks"][sport] = int(r["rank"])
    previous = _previous()
    for w in wallets.values():
        for sport in sports:
            if w["wallet"] in boards[sport].index:
                r = boards[sport].loc[w["wallet"]]
                w["clv"][sport] = _figures(r, int(r["rank"]))
            elif sport in stats and w["wallet"] in stats[sport].index:
                w["clv"][sport] = _figures(stats[sport].loc[w["wallet"]], None)
            elif (w["wallet"], sport) in previous:
                w["clv"][sport] = previous[(w["wallet"], sport)]
    return {"sports": sports, "wallets": list(wallets.values()), "top_n": top_n}


def write_watched(data: dict, path: Path = None) -> None:
    """The embedded figures as a table: the record of what the page showed."""
    rows = [{"wallet": w["wallet"], "name": w["name"], "sport": sport, **fig,
             "watched_in": ",".join(sorted(w["ranks"])),
             "alltime_pnl": (w.get("alltime") or {}).get("pnl"), "alltime_vol": (w.get("alltime") or {}).get("vol"),
             "pi_pnl": (w.get("pi") or {}).get("pnl"), "pi_win_rate": (w.get("pi") or {}).get("win_rate")}
            for w in data["wallets"] for sport, fig in w["clv"].items()]
    cols = ["wallet", "name", "sport", *FIGURES, "watched_in", "alltime_pnl", "alltime_vol", "pi_pnl", "pi_win_rate"]
    df = pd.DataFrame(rows, columns=cols)
    for col in ("rank", "alltime_pnl", "alltime_vol"):
        df[col] = df[col].astype("Int64")                # blank where there is no figure
    df.to_csv(path or WATCHED, index=False)


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
    alltime(data["wallets"])
    second_opinion(data["wallets"])
    data["prefixes"] = sport_prefixes()
    data["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(data, TEMPLATE.read_text()))
    write_watched(data)
    ranked = ", ".join(f"{sport} {info['ranked']}" for sport, info in data["sports"].items())
    print(f"{args.out}: {len(data['wallets'])} wallets watched ({ranked} ranked), "
          f"{len(data['prefixes'])} league codes")


if __name__ == "__main__":
    main()
