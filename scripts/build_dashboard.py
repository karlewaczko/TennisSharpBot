#!/usr/bin/env python3
"""Build the JSON payload behind the live value dashboard.

    python scripts/build_dashboard.py -o data/dashboard.json

For every scheduled match it records the market price, Pinnacle's price
where available, the model's probability, the implied fair odds and the
resulting edge -- everything the dashboard renders, computed here rather
than in the page, so the numbers are auditable from the command line.

Pinnacle coverage on TennisExplorer is partial (it appeared in roughly one
match in six in an evening sample). Rather than dropping those matches or
quietly substituting another book, each row carries `ref_book` naming the
book actually used as the sharp reference, and the dashboard shows it.

Matches where either player is below MIN_MATCHES_PLAYED are excluded from
the value table and counted separately: an unrated player sits at the
default 1500 Elo, which manufactures a large fake edge -- the most
attractive-looking and least real signal this model can produce.

The schedule feed is also the results feed (see tennisexplorer's module
docstring): a row keeps its odds after the match is over, so finished and
in-play matches have to be filtered out explicitly -- see `unplayed_mask`.
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from tennissharp import config, odds_math, tourney_matching
from tennissharp.backtest import DEFAULT_EDGE_THRESHOLD, MIN_MATCHES_PLAYED
from tennissharp.data import tennisexplorer as te
from tennissharp.model import feature_columns
from tennissharp.value_finder import _features_for_matchup

_spec = importlib.util.spec_from_file_location(
    "analyze_match", Path(__file__).parent / "analyze_match.py")
_am = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_am)
resolve_name = _am.resolve_name

# What counts as a real event. ITF, UTR Pro Series and the Swiss league are
# excluded: neither our Elo nor Tennis Abstract rates those fields (TA's own
# cutoff is ITF $50K+), so every such match would be dropped anyway after
# costing an odds-history request.
EXCLUDE_EVENTS = "UTR|Nationalliga|ITF"
# Main tour first, then challengers, so a capped run spends its budget where
# the model has the most history.
CHALLENGER_MARKER = "challenger"
SHARP_BOOKS = ("Pinnacle", "Betfair")

# A two-way tennis market runs 2-3% overround at Pinnacle and rarely past 15%
# at the softest book (median on a full card: 10%). Anything far beyond that
# is not a price. TennisExplorer lists placeholder pairs like 1.02/1.02 and
# 1.03/1.03 -- a 94-96% "margin" -- for matches nobody has priced yet, and
# de-vigging those produced a 60% negative EV out of thin air.
MAX_REF_MARGIN = 0.30

# `best_of` is a trained feature: five-setters give the stronger player more
# chances to assert himself, so the same Elo gap converts to a higher win
# probability than over three sets. Every match was scored as best-of-three
# until now, which was harmless while the card held no majors and wrong for
# 104 US Open matches the moment one started.
GRAND_SLAMS = ("australian open", "roland garros", "french open", "wimbledon", "us open")


def best_of_for(tournament: str, tour: str) -> int:
    """Men's Grand Slam main draws only. Women play three sets at the majors,
    and men's qualifying is best-of-three too -- TennisExplorer lists that
    under its own tournament name, so it never reaches this test."""
    if tour != "atp":
        return 3
    name = str(tournament).lower()
    return 5 if any(slam in name for slam in GRAND_SLAMS) else 3


def margin(odds) -> float:
    return sum(1 / x for x in odds) - 1


def is_priced(odds) -> bool:
    """A quote pair that could plausibly be a real market."""
    if any(x is None or x <= 1.0 for x in odds):
        return False
    return 0.0 <= margin(odds) <= MAX_REF_MARGIN


# Tennis Abstract's own Elo, used only where our model has too little history.
# Their pool is much wider than ours -- it counts tour-level qualifying,
# challengers and ITF $50K+ events, which tennis-data.co.uk does not carry --
# so it rates players our own Elo has never seen. On the current card that is
# 15 of the 23 matches we would otherwise drop entirely.
#
# This is a *different method*, not a fallback value slotted into the model:
# the model is trained on our Elo's scale with the market price as a feature,
# so feeding another provider's ratings into it would be an input it never saw.
# Instead these matches carry Tennis Abstract's own forecast, computed with the
# standard Elo formula their methodology note specifies, and are labelled as
# such in the payload so the page never presents them as model output.
#
# Formula verified against the five reference points they publish: 100 points
# -> 64%, 200 -> 76%, 300 -> 85%, 400 -> 91%, 500 -> 95%.
TA_SURFACE_COLUMN = {"hard": "helo", "clay": "celo", "grass": "gelo"}


def _ta_elo_probability(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** (-(elo_a - elo_b) / 400.0))


# A played match keeps its pre-match odds on the schedule page, so nothing in
# the odds columns distinguishes it from an upcoming one.
PLAY_MARKERS = ("score", "sets_won1", "sets_won2")


def unplayed_mask(sched: pd.DataFrame) -> pd.Series:
    """True for matches that have not started yet.

    Both marker kinds are needed. `score` (games per completed set) is absent
    while the opening set is still running, and `sets_won*` is absent for a
    match decided by retirement inside the first set -- on the card that first
    exposed this, Fritz/Nakashima carried a full score and Quevedo/Jones only
    a set count. Either marker present means the match is over or under way,
    and either way it does not belong on a page of upcoming value.
    """
    started = pd.Series(False, index=sched.index)
    for col in PLAY_MARKERS:
        if col in sched.columns:
            started |= sched[col].notna()
    return ~started


def _sharp_reference(match_id):
    """(book, [odds_a, odds_b], players) from the sharpest book quoting this
    match, preferring Pinnacle, then Betfair, then lowest margin."""
    try:
        hist = te.fetch_match_odds_history(match_id)
    except Exception:
        return None
    if hist.empty:
        return None
    cur = hist.sort_values("timestamp").groupby(["bookmaker", "player"]).last().reset_index()
    players = sorted(cur["player"].unique())
    if len(players) != 2:
        return None

    def quotes(book):
        rows = [cur[(cur["bookmaker"] == book) & (cur["player"] == pl)] for pl in players]
        if any(len(r) == 0 for r in rows):
            return None
        return [float(r["odds"].iloc[0]) for r in rows]

    # A sharp book is preferred only while it is actually quoting the match:
    # Betfair carries 1.03/1.03 placeholders for unpriced draws, and taking
    # those on the strength of the book's name is worse than any soft price.
    for book in SHARP_BOOKS:
        q = quotes(book)
        if q and is_priced(q):
            return book, q, players

    best, best_q, best_margin = None, None, None
    for book in cur["bookmaker"].unique():
        q = quotes(book)
        if not q or not is_priced(q):
            continue
        if best_margin is None or margin(q) < best_margin:
            best, best_q, best_margin = book, q, margin(q)
    return (best, best_q, players) if best else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", type=Path, default=config.PROCESSED_DIR / "dashboard.json")
    ap.add_argument("--limit", type=int, default=200,
                    help="max matches; each costs one odds-history request (~2-4s)")
    ap.add_argument("--tour", choices=("atp", "wta", "both"), default="both")
    ap.add_argument("--no-challenger", action="store_true")
    ap.add_argument("--date", action="append", metavar="YYYY-MM-DD",
                    help="restrict to these playing days; repeatable")
    ap.add_argument("--threshold", type=float, default=DEFAULT_EDGE_THRESHOLD)
    args = ap.parse_args()

    sched = pd.read_csv(config.PROCESSED_DIR / "tennisexplorer_upcoming.csv")
    sched = sched[~sched["tournament"].str.contains(EXCLUDE_EVENTS, na=False, regex=True,
                                                     case=False)]
    sched = sched[sched["odds1"].notna() & sched["odds2"].notna()]
    n_finished = int((~unplayed_mask(sched)).sum())
    sched = sched[unplayed_mask(sched)]
    if args.date:
        if "date" not in sched.columns:
            raise SystemExit("Der Spielplan hat keine date-Spalte -- "
                             "bitte zuerst scripts/update_data.py neu laufen lassen.")
        sched = sched[sched["date"].isin(args.date)]
    if args.tour in ("atp", "wta"):
        suffix = "-men/" if args.tour == "atp" else "-women/"
        sched = sched[sched["tournament_url"].str.contains(suffix, regex=False, na=False)]
    if args.no_challenger:
        sched = sched[~sched["tournament"].str.contains(CHALLENGER_MARKER, case=False, na=False)]

    is_ch = sched["tournament"].str.contains(CHALLENGER_MARKER, case=False, na=False)
    sched = (sched.assign(_tier=is_ch.astype(int))
                  .sort_values("_tier", kind="stable")
                  .drop(columns="_tier")
                  .head(args.limit))

    state = joblib.load(config.MODELS_DIR / "live_state.joblib")
    model = joblib.load(config.MODELS_DIR / "win_probability_model.joblib")
    snapshot = state.elo.snapshot()
    roster = snapshot["player"].tolist()
    played = dict(zip(snapshot["player"], snapshot["matches_played"]))
    elo_overall = dict(zip(snapshot["player"], snapshot["elo_overall"]))

    ta = pd.concat([pd.read_csv(config.PROCESSED_DIR / f"ta_elo_{t}_general.csv")
                    for t in ("wta", "atp")], ignore_index=True)
    ta_names = ta["player"].tolist()
    ta_by_name = ta.set_index("player")

    def ta_rating(query: str, surface: str):
        """(display name, rating) from Tennis Abstract, surface-specific where
        they publish one -- their note says the surface blends forecast
        individual matches better than the overall number."""
        hit = resolve_name(query, ta_names)
        if not hit:
            return None
        row = ta_by_name.loc[hit]
        col = TA_SURFACE_COLUMN.get(surface.lower())
        for candidate in (col, "elo"):
            if candidate and candidate in row and pd.notna(row[candidate]):
                return hit, float(row[candidate])
        return None

    # Tennis Abstract's per-edition surface-speed report doubles as the only
    # court-surface source we have for a named tournament. It covers the tour
    # calendar, not the challenger circuit, so most challengers fall through
    # to the neutral default -- as they did before, just now on purpose.
    speed_hist = pd.read_csv(config.PROCESSED_DIR / "ta_surface_speed_history.csv",
                             parse_dates=["date"])
    speed_index = tourney_matching.build_surface_speed_index(speed_hist)
    surface_by_name = {}
    for row in speed_hist.sort_values("date").itertuples():
        surface_by_name[tourney_matching.normalize_tourney_name(row.tournament)] = row.surface

    def court_surface(tournament: str) -> str:
        key = tourney_matching.normalize_tourney_name(tournament)
        if key in surface_by_name:
            return str(surface_by_name[key])
        for name, surf in surface_by_name.items():
            if name and (key in name or name in key):
                return str(surf)
        return "Hard"

    today = pd.Timestamp.now().normalize()
    matches, skipped = [], []
    for _, m in sched.iterrows():
        a = resolve_name(str(m["player1"]), roster, weight=played.get)
        b = resolve_name(str(m["player2"]), roster, weight=played.get)
        label = f"{m['player1']} vs {m['player2']}"

        thin_reason = None
        if not a or not b or a == b:
            thin_reason = "Spieler nicht in unserer Historie"
        elif min(played.get(a, 0), played.get(b, 0)) < MIN_MATCHES_PLAYED:
            thin = a if played.get(a, 0) < played.get(b, 0) else b
            thin_reason = f"{thin}: nur {played.get(thin, 0):.0f} Matches bei uns"

        # Our own Elo is too thin -- fall back to Tennis Abstract's rating if
        # it covers both players, rather than dropping the match.
        ta_fallback = None
        if thin_reason:
            court = court_surface(str(m["tournament"]))
            ra = ta_rating(str(m["player1"]), court)
            rb = ta_rating(str(m["player2"]), court)
            if ra and rb:
                ta_fallback = (ra, rb)
            else:
                skipped.append({"match": label, "tournament": str(m["tournament"]),
                                "reason": thin_reason + " und kein Tennis-Abstract-Elo"})
                continue

        ref = _sharp_reference(m["match_id"])
        if ref is None:
            ref_book, ref_odds = "TennisExplorer", [float(m["odds1"]), float(m["odds2"])]
            ref_players = [str(m["player1"]), str(m["player2"])]
        else:
            ref_book, ref_odds, ref_players = ref

        # No book is quoting a plausible two-way price. Without a market there
        # is nothing to be right or wrong about, so the match is dropped
        # rather than scored against a placeholder.
        if not is_priced(ref_odds):
            skipped.append({"match": label, "tournament": str(m["tournament"]),
                            "reason": f"keine belastbaren Quoten "
                                      f"({ref_odds[0]:.2f}/{ref_odds[1]:.2f}, "
                                      f"Marge {margin(ref_odds) * 100:.0f}%)"})
            continue

        tour = "wta" if "-women/" in str(m["tournament_url"]) else "atp"
        surface = court_surface(str(m["tournament"]))
        best_of = best_of_for(str(m["tournament"]), tour)
        speed = tourney_matching.lookup_surface_speed(
            speed_index, dt.date.today().year, str(m["tournament"]))

        stale = []
        if ta_fallback:
            (name_a, elo_a), (name_b, elo_b) = ta_fallback
            method, label_a, label_b = "ta_elo", name_a, name_b
            elos = (elo_a, elo_b)
            counts = (None, None)
            p_a = _ta_elo_probability(elo_a, elo_b)
            first_is_a = resolve_name(ref_players[0], [name_a, name_b]) == name_a
        else:
            method, label_a, label_b = "model", a, b
            elos = (float(elo_overall.get(a, float("nan"))),
                    float(elo_overall.get(b, float("nan"))))
            counts = (int(played.get(a, 0)), int(played.get(b, 0)))
            first_is_a = resolve_name(ref_players[0], [a, b]) != b
            stale = [p for p in (a, b) if state.is_stale(p, today)]

        # Orient the reference prices onto (first player, second player).
        if not first_is_a:
            ref_odds = [ref_odds[1], ref_odds[0]]

        fair_a, fair_b = odds_math.shin_devig(ref_odds)

        if not ta_fallback:
            feats = _features_for_matchup(state, a, b, surface, best_of, speed)
            clipped = float(np.clip(fair_a, 1e-6, 1 - 1e-6))
            feats["market_logit"] = float(np.log(clipped / (1 - clipped)))
            p_a = float(model.predict_proba(pd.DataFrame([feats])[feature_columns(True)])[0][1])

        sides = []
        for name, prob, fair, ref_price, elo, n in (
            (label_a, p_a, fair_a, ref_odds[0], elos[0], counts[0]),
            (label_b, 1 - p_a, fair_b, ref_odds[1], elos[1], counts[1]),
        ):
            sides.append({
                "player": name,
                "model_prob": round(prob, 4),
                "model_fair_odds": round(1 / prob, 3) if prob > 0 else None,
                "market_prob": round(fair, 4),
                "market_fair_odds": round(1 / fair, 3) if fair > 0 else None,
                "ref_odds": round(ref_price, 3),
                "edge": round(odds_math.edge(prob, fair), 4),
                "ev_at_ref": round(prob * ref_price - 1, 4),
                "elo": round(elo, 1),
                "matches": n,
            })

        matches.append({
            "match_id": str(m["match_id"]),
            "date": str(m["date"]) if pd.notna(m.get("date")) else None,
            "tournament": str(m["tournament"]),
            "tour": tour,
            "surface": surface,
            "best_of": best_of,
            "ref_book": ref_book,
            "ref_margin": round(margin(ref_odds), 4),
            # "model" = our trained classifier with the market price blended in.
            # "ta_elo" = Tennis Abstract's rating through their published Elo
            # formula, no market input. Never mix the two in one comparison.
            "method": method,
            "sides": sides,
            # Players whose last match in our feed is old enough that their
            # rest/form/fatigue features describe the gap, not the player.
            "stale_players": stale,
            "best_edge": round(max(s["edge"] for s in sides), 4),
            # Only the trained model's disagreements are treated as signals.
            # A pure-Elo forecast carries no market information at all, and it
            # shows: measured on this card the model sits 1.5% from the market
            # on average (3% of sides past 5%), the Elo fallback 10.6% (60% of
            # sides past 5%, worst 25.6%). Against a market our own audit finds
            # calibrated to within 0.8pp, that gap is the rating being
            # incomplete, not the price being wrong -- so these rows are shown
            # for coverage and are never scored as value.
            #
            # A stale row is excluded for the same reason. The first two
            # signals this dashboard ever produced were both of that kind:
            # Smith (last seen 2026-03-31) and Pigossi (2025-09-11) each read
            # as maximally rested against an opponent we still track, and in
            # Smith's case every other feature -- Elo -257, surface Elo -77,
            # form -0.30 -- pointed the other way.
            "signal": (method == "model" and not stale
                       and max(s["edge"] for s in sides) > args.threshold),
        })

    matches.sort(key=lambda x: x["best_edge"], reverse=True)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "threshold": args.threshold,
        "n_scheduled": int(len(sched)),
        "n_finished": n_finished,
        "n_scored": len(matches),
        "n_signals": sum(1 for m in matches if m["signal"]),
        "n_by_method": {meth: sum(1 for m in matches if m["method"] == meth)
                        for meth in sorted({m["method"] for m in matches})},
        "dates": sorted({m["date"] for m in matches if m["date"]}),
        "ref_books": {b: sum(1 for m in matches if m["ref_book"] == b)
                      for b in sorted({m["ref_book"] for m in matches})},
        "matches": matches,
        "skipped": skipped,
        # Carried into the page so the dashboard cannot be read as a
        # profitability claim -- these are this repo's own audit numbers.
        "audit": {
            "information_gain": -0.00078,
            "matches_tested": 55124,
            "backtest_roi": 0.0135,
            "backtest_t": 0.48,
            "backtest_n": 1898,
        },
    }
    args.out.write_text(json.dumps(payload, indent=1))
    print(f"{payload['n_scored']} Partien bewertet, {payload['n_signals']} Signale, "
          f"{len(skipped)} uebersprungen, {n_finished} bereits gespielt -> {args.out}")
    print("Referenzbuecher:", payload["ref_books"])


if __name__ == "__main__":
    main()
