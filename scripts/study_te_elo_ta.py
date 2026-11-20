#!/usr/bin/env python3
"""Does Tennis Abstract's Elo help our own (TE-Elo)?

    python scripts/study_te_elo_ta.py

Replays the cached result pages (scripts/update_te_elo.py --rebuild fills
data/raw/te_results/) and, for every match since the first weekly Tennis
Abstract snapshot in data/processed/ta_elo_history.csv, takes both players'
ratings as they stood before it: ours, and Tennis Abstract's from the
latest snapshot on or before the match day. The scale between the two is
fitted on the first snapshot only, so nothing after a match informs its
forecast. Scored three ways against the results and the de-vigged odds:

  both rated by Tennis Abstract: its Elo against ours
  only one rated by it: its Elo against ours on its scale ("mixed") against ours alone
  neither: ours alone

and, for the first two, blends of Tennis Abstract's forecast and ours.

Results go to data/reports/te_elo_ta.json.
"""
import _bootstrap  # noqa: F401
import importlib.util
import json
import math
import sys
from pathlib import Path

import pandas as pd

from tennissharp import config, te_elo
from tennissharp.elo import expected_score

OUT = config.REPORTS_DIR / "te_elo_ta.json"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def book_for(snap: pd.DataFrame, bd):
    """A ProfileBook over one Tennis Abstract snapshot."""
    frames = {}
    for tour, g in snap.groupby("tour"):
        g = g.assign(matches=1, matches_with_stats=0, spw=0.62)
        frames[tour] = g
    return bd.ProfileBook(frames)


def blends(rec: list[dict]) -> dict:
    """Log loss of w * Tennis Abstract + (1 - w) * ours, in log-odds, per w."""
    logit = lambda p: math.log(p / (1 - p))  # noqa: E731
    out = {}
    for w in (0.0, 0.25, 0.5, 0.75, 1.0):
        mixed = [{**x, "p": 1 / (1 + math.exp(-(w * logit(x["p"]) + (1 - w) * logit(x["ours"]))))} for x in rec]
        out[str(w)] = te_elo.score(mixed).get("log_loss")
    return out


def main() -> None:
    bd, up = _load("build_dashboard"), _load("update_te_elo")
    hist = pd.read_csv(config.PROCESSED_DIR / "ta_elo_history.csv")
    dates = sorted(hist["ta_updated"].unique())
    books = {d: book_for(hist[hist["ta_updated"] == d], bd) for d in dates}
    meta = json.loads(up.META.read_text())
    rows = pd.concat([te_elo.results(pd.read_csv(p, dtype={"match_id": str, "time": str}))
                      for p in sorted(up.CACHE.glob("*.csv"))], ignore_index=True)
    rows = rows.sort_values(["date", "time"], kind="stable")
    r = te_elo.Ratings(meta.get("start"))
    r.play(rows[rows["date"] < dates[0]])

    cache: dict = {}

    tour_of = {"M": "atp", "W": "wta"}

    def ta_of(slug, day):
        p = r.players[slug]
        snap = max(d for d in dates if d <= day)
        key = (slug, snap)
        if key not in cache:
            hit = books[snap].resolve(p.name, tour_of[p.sex]) if p.sex in tour_of else None
            cache[key] = float(hit["elo"]) if hit is not None and pd.notna(hit.get("elo")) else None
        return cache[key]

    scale, n_pairs = {}, {}
    for sex, tour in tour_of.items():
        pairs = [(p.elo, e) for s, p in r.players.items() if p.matches >= te_elo.SCALE_MIN_MATCHES and p.sex == sex
                 if (e := ta_of(s, dates[0])) is not None]
        scale[tour], n_pairs[tour] = te_elo.fit_scale(pairs), len(pairs)
        print(f"{tour}: Skala aus {len(pairs)} Spielern: {scale[tour]}", flush=True)

    rec = {"both": [], "both_te": [], "mixed": [], "mixed_te": [], "none": []}
    for x in rows[rows["date"] >= dates[0]].itertuples(index=False):
        pw, pl = r.players.get(x.winner), r.players.get(x.loser)
        if pw and pl:
            ours = expected_score(pw.elo, pl.elo)
            tw, tl = ta_of(x.winner, x.date), ta_of(x.loser, x.date)
            sc = scale.get(tour_of.get(pw.sex or pl.sex, ""))
            base = {"odds_w": x.odds_w, "odds_l": x.odds_l, "date": x.date, "level": x.level,
                    "n_min": min(pw.matches, pl.matches)}
            if tw is not None and tl is not None:
                rec["both"].append({**base, "p": expected_score(tw, tl), "ours": ours})
                rec["both_te"].append({**base, "p": ours})
            elif (tw is not None or tl is not None) and sc:
                a = tw if tw is not None else te_elo.on_ta_scale(pw.elo, sc)
                b = tl if tl is not None else te_elo.on_ta_scale(pl.elo, sc)
                rec["mixed"].append({**base, "p": expected_score(a, b), "ours": ours})
                rec["mixed_te"].append({**base, "p": ours})
            else:
                rec["none"].append({**base, "p": ours})
        r.update(x)

    report = {"since": dates[0], "snapshots": dates, "scale": scale, "scale_players": n_pairs,
              "both_rated_by_ta": {"ta": te_elo.score(rec["both"]), "ours": te_elo.score(rec["both_te"])},
              "one_rated_by_ta": {"mixed": te_elo.score(rec["mixed"]), "ours": te_elo.score(rec["mixed_te"])},
              "neither": te_elo.score(rec["none"]),
              # Tennis Abstract's weight w in a blend of log-odds, w * TA + (1 - w) * ours
              "blend_both": blends(rec["both"]), "blend_one": blends(rec["mixed"])}
    OUT.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
