#!/usr/bin/env python3
"""Opening versus closing: does the tennis line move in a predictable
direction, and does any book's price beat Pinnacle's close?

    python scripts/study_line_movement.py --days 3 --limit 150

TennisExplorer's match pages keep every bookmaker's full odds history with
timestamps, the oldest entry marked "Opening odds". For matches already
decided this gives, per book and side, the opening price, the closing price
(the last recorded change) and the result -- enough to measure the one lead
the research report left open: whether betting early carries value.

Three questions, all settled against Pinnacle's *closing* de-vigged price,
the sharpest number the market produces:

1. Movement: how far does Pinnacle move from open to close, and does the
   opening favourite tend to shorten (money follows favourites) or drift?
2. Closing-line value of opening prices: a bettor who took Pinnacle's
   opening price on the favourite / on the underdog -- what CLV did that
   buy, and what did it return at the logged odds?
3. Soft books at the close: how often does a soft book's last price still
   sit above Pinnacle's closing fair value, i.e. how much "top-down" value
   is left on the table at the start of play?

Numbers are written to data/reports/line_movement.json and printed.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import json
import time

import numpy as np
import pandas as pd

from tennissharp import config, odds_math
from tennissharp.data import tennisexplorer as te

EXCLUDE = "UTR|Nationalliga|Futures|ITF"
REQUEST_PAUSE = 1.5
SOFT_BOOKS = ("bet365", "bwin", "Unibet", "Betway", "William Hill", "Interwetten",
              "Betsson", "10Bet", "BetVictor", "Coral", "Ladbrokes", "bet-at-home", "1xBet")


def open_close(hist: pd.DataFrame) -> dict:
    """{book -> {player -> (opening_odds, closing_odds)}} from one match's history."""
    out = {}
    if hist.empty:
        return out
    for (book, player), grp in hist.sort_values("timestamp").groupby(["bookmaker", "player"]):
        opening = grp[grp["is_opening"]]
        first = float(opening["odds"].iloc[-1]) if len(opening) else float(grp["odds"].iloc[0])
        last = float(grp["odds"].iloc[-1])
        out.setdefault(book, {})[player] = (first, last)
    return out


def analyse(records: list[dict]) -> dict:
    """The measurements, from per-match records produced by `collect`."""
    df = pd.DataFrame(records)
    res = {"n_matches": int(len(df))}
    if df.empty:
        return res
    # 1. Movement at Pinnacle.
    p = df.dropna(subset=["pin_open_fav", "pin_close_fav"])
    res["pinnacle"] = {
        "n": int(len(p)),
        "mean_abs_move_prob": round(float((p["pin_close_fav_prob"] - p["pin_open_fav_prob"]).abs().mean()), 4),
        "favourite_shortened_share": round(float((p["pin_close_fav_prob"] > p["pin_open_fav_prob"]).mean()), 3),
        "favourite_drifted_share": round(float((p["pin_close_fav_prob"] < p["pin_open_fav_prob"]).mean()), 3),
        # CLV of taking Pinnacle's OPENING price, judged at Pinnacle's CLOSE.
        "clv_open_favourite": round(float((p["pin_open_fav"] * p["pin_close_fav_prob"] - 1).mean()), 4),
        "clv_open_underdog": round(float((p["pin_open_dog"] * (1 - p["pin_close_fav_prob"]) - 1).mean()), 4),
        # Realised return of the same two habits at the opening price.
        "roi_open_favourite": round(float(np.where(p["fav_won"], p["pin_open_fav"] - 1, -1.0).mean()), 4),
        "roi_open_underdog": round(float(np.where(~p["fav_won"], p["pin_open_dog"] - 1, -1.0).mean()), 4),
        "favourite_win_rate": round(float(p["fav_won"].mean()), 3),
        "closing_fair_favourite_mean": round(float(p["pin_close_fav_prob"].mean()), 3),
    }
    # 3. Soft books at the close against Pinnacle's closing fair value.
    s = df[df["soft_sides_checked"] > 0]
    res["soft_at_close"] = {
        "n_matches": int(len(s)),
        "sides_checked": int(s["soft_sides_checked"].sum()),
        "sides_above_pinnacle_fair": int(s["soft_sides_positive"].sum()),
        "share_above_fair": (round(float(s["soft_sides_positive"].sum() / s["soft_sides_checked"].sum()), 4)
                             if s["soft_sides_checked"].sum() else None),
        "mean_ev_of_positive_sides": (round(float(np.mean([x for xs in s["soft_pos_evs"] for x in xs])), 4)
                                      if any(len(xs) for xs in s["soft_pos_evs"]) else None),
        "best_side": max((x for xs in s["soft_best"] for x in [xs] if x), key=lambda x: x["ev"], default=None),
    }
    return res


def collect(days: int, limit: int, sleep=time.sleep) -> list[dict]:
    frames = []
    for d in range(-days, 0):
        frames.append(te.fetch_matches(d))
        sleep(1.0)
    done = pd.concat(frames, ignore_index=True)
    done = done[done["sets_won1"].notna() & done["sets_won2"].notna()
                & done["odds1"].notna() & (done["sets_won1"] != done["sets_won2"])]
    done = done[~done["tournament"].str.contains(EXCLUDE, case=False, na=False, regex=True)]
    done = done.drop_duplicates(subset="match_id").head(limit)
    records = []
    for m in done.itertuples(index=False):
        try:
            hist, _ = te.fetch_match_detail(m.match_id)
        except Exception:
            continue
        sleep(REQUEST_PAUSE)
        oc = open_close(hist)
        if "Pinnacle" not in oc or len(oc["Pinnacle"]) != 2:
            continue
        players = sorted(oc["Pinnacle"])
        pin = oc["Pinnacle"]
        open_pair = [pin[pl][0] for pl in players]
        close_pair = [pin[pl][1] for pl in players]
        if any(x <= 1.0 for x in open_pair + close_pair):
            continue
        open_fair = odds_math.shin_devig(open_pair)
        close_fair = odds_math.shin_devig(close_pair)
        fav = 0 if open_fair[0] >= open_fair[1] else 1          # favourite at the open
        dog = 1 - fav
        # Who won, in the odds table's player order.
        winner_sched = m.player1 if m.sets_won1 > m.sets_won2 else m.player2
        winner_idx = None
        for i, pl in enumerate(players):
            if str(pl).strip() == str(winner_sched).strip():
                winner_idx = i
        if winner_idx is None:
            # Fall back to surname match.
            for i, pl in enumerate(players):
                if str(pl).split(" ")[0].lower() == str(winner_sched).split(" ")[0].lower():
                    winner_idx = i
        if winner_idx is None:
            continue
        soft_checked = soft_pos = 0
        soft_evs, best = [], None
        for book in SOFT_BOOKS:
            if book not in oc or len(oc[book]) != 2:
                continue
            for i, pl in enumerate(players):
                close_price = oc[book][pl][1]
                if close_price <= 1.0:
                    continue
                soft_checked += 1
                ev = close_fair[i] * close_price - 1
                if ev > 0:
                    soft_pos += 1
                    soft_evs.append(round(ev, 4))
                    if best is None or ev > best["ev"]:
                        best = {"match": f"{players[0]} v {players[1]}", "tournament": m.tournament,
                                "book": book, "side": pl, "odds": close_price,
                                "pinnacle_fair": round(1 / close_fair[i], 3), "ev": round(ev, 4)}
        records.append({
            "match_id": m.match_id, "tournament": m.tournament, "date": m.date,
            "players": players,
            "pin_open_fav": open_pair[fav], "pin_open_dog": open_pair[dog],
            "pin_close_fav": close_pair[fav],
            "pin_open_fav_prob": open_fair[fav], "pin_close_fav_prob": close_fair[fav],
            "fav_won": winner_idx == fav,
            "soft_sides_checked": soft_checked, "soft_sides_positive": soft_pos,
            "soft_pos_evs": soft_evs, "soft_best": best,
        })
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="past days to read results from")
    ap.add_argument("--limit", type=int, default=150, help="max matches (one request each)")
    args = ap.parse_args()
    records = collect(args.days, args.limit)
    result = {"measured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "days": args.days, **analyse(records)}
    (config.REPORTS_DIR / "line_movement.json").write_text(json.dumps(result, indent=1, default=str))
    pd.DataFrame(records).drop(columns=["soft_pos_evs", "soft_best"], errors="ignore").to_csv(
        config.REPORTS_DIR / "line_movement_matches.csv", index=False)
    print(json.dumps(result, indent=1, default=str))


if __name__ == "__main__":
    main()
