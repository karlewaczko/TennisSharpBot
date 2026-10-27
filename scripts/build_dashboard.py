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

Besides the model table the payload carries a *price board*: every book on
the match page plus Polymarket and Kalshi, each side's EV against the sharp
fair value, and the best-price pair per match (an arbitrage when it sums
below one). That part needs no rating, so it also covers ITF matches the
model never scores. Each run appends its quotes to odds_snapshots.csv and
its positive-EV sides to picks_log.csv, the raw material for measuring
opening-vs-closing movement and closing-line value later.

Last, `all_matches` lists every singles match of today and tomorrow, each
joined with the weekly player table and whatever the run above learned
about it -- the page's complete match list (see `all_matches_board`).
"""
import _bootstrap  # noqa: F401
import argparse
import datetime as dt
import importlib.util
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import pandas as pd

from tennissharp import config, market_compare as mc, odds_math, player_stats as ps, tourney_matching
from tennissharp.elo import normalize_surface
from tennissharp.backtest import DEFAULT_EDGE_THRESHOLD, MIN_MATCHES_PLAYED
from tennissharp.data import (kalshi, polymarket, polymarket_traders as pt,
                              tennisabstract_forecast as taf, tennisexplorer as te,
                              tennismylife as tml)
from tennissharp.value_finder import matchup_probability

_spec = importlib.util.spec_from_file_location(
    "analyze_match", Path(__file__).parent / "analyze_match.py")
_am = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_am)
resolve_name = _am.resolve_name

# What counts as a real event. ITF, UTR Pro Series, the Swiss league and the
# site's collective "Futures" band are excluded: neither our Elo nor Tennis
# Abstract rates those fields (TA's own cutoff is ITF $50K+), so every such
# match would be dropped anyway after costing an odds-history request.
EXCLUDE_EVENTS = "UTR|Nationalliga|ITF|Futures"
# The price board is wider than the model: ITF matches stay in it when a
# prediction market quotes them, because comparing prices needs no rating.
PRICE_BOARD_EXCLUDE = "UTR|Nationalliga|Futures"
# Main tour first, then challengers, so a capped run spends its budget where
# the model has the most history.
CHALLENGER_MARKER = "challenger"
SHARP_BOOKS = mc.SHARP_BOOKS

# A two-way tennis market runs 2-3% overround at Pinnacle and rarely past 15%
# at the softest book (median on a full card: 10%). Anything far beyond that
# is not a price. TennisExplorer lists placeholder pairs like 1.02/1.02 and
# 1.03/1.03 -- a 94-96% "margin" -- for matches nobody has priced yet, and
# de-vigging those produced a 60% negative EV out of thin air.
MAX_REF_MARGIN = 0.30

# `best_of` is a trained feature: five-setters give the stronger player more
# chances to assert himself, so the same Elo gap converts to a higher win
# probability than over three sets.
GRAND_SLAMS = ("australian open", "roland garros", "french open", "wimbledon", "us open")


def best_of_for(tournament: str, tour: str, is_qualifying: bool = False) -> int:
    """Five sets only in a men's Grand Slam *main draw*.

    Qualifying at the majors is best of three, and the schedule page gives it
    the same tournament name and the same URL as the main draw -- so the name
    alone cannot tell them apart. Reading it as a five-setter mis-scored 70
    finished US Open qualifying matches before the round came from the
    match-detail page instead.
    """
    if tour != "atp" or is_qualifying:
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


# The dashboard publishes these figures. They were literals in this file
# until a data refresh moved the information gain from -0.00078 to -0.00111
# and the page went on claiming the old number for days -- so they are read
# from the audit's own output now, with the last measured values as a
# fallback for a checkout that has not run scripts/audit_edge.py yet.
AUDIT_FALLBACK = {
    "information_gain": -0.00111,
    "matches_tested": 55124,
    "backtest_roi": 0.0135,
    "backtest_t": 0.48,
    "backtest_n": 1898,
}


def audit_numbers() -> dict:
    out = dict(AUDIT_FALLBACK)
    path = config.PROCESSED_DIR / "edge_audit_summary.json"
    try:
        measured = json.loads(path.read_text())
    except (OSError, ValueError):
        return out
    for key in ("information_gain", "matches_tested"):
        if measured.get(key) is not None:
            out[key] = measured[key]
    out["measured_at"] = measured.get("measured_at")
    return out


def start_times(sched: pd.DataFrame) -> pd.Series:
    """UTC kick-off per row from the schedule's date and time columns
    (NaT where the page gave no time)."""
    if "date" not in sched.columns or "time" not in sched.columns:
        return pd.Series(pd.NaT, index=sched.index, dtype="datetime64[ns, UTC]")
    stamp = sched["date"].astype(str) + " " + sched["time"].astype(str)
    return pd.to_datetime(stamp, format="%Y-%m-%d %H:%M", errors="coerce", utc=True)


def started_mask(sched: pd.DataFrame, now=None) -> pd.Series:
    """True for matches whose listed start lies in the past.

    The score markers below catch a match once a set is in; this catches
    the gap before that, when a match is under way, its pre-match odds are
    still on the page and the prediction markets are already trading
    in-play. Three "arbitrages" on the first card built with the markets
    were exactly that: a live Kalshi price against a pre-match schedule
    quote on a match in its second set."""
    now = pd.Timestamp(now or pd.Timestamp.now(tz="UTC")).tz_convert("UTC")
    starts = start_times(sched)
    return starts.notna() & (starts <= now)


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


# A player our own feed lost track of may simply have been playing where it
# does not look. TennisMyLife covers challengers, qualifying and a wider WTA
# field; on the card that first carried this check, 7 of the 8 players marked
# stale had played within the last three weeks according to that source.
RECENT_DAYS = 60


def load_recent_play(path=None) -> dict:
    """{player -> last match date} from TennisMyLife, empty if not built."""
    path = path or config.PROCESSED_DIR / "tml_last_seen.pkl"
    try:
        return pd.read_pickle(path)
    except (OSError, ValueError, EOFError):
        return {}


def still_stale(player, state, today, recent, names) -> bool:
    """True only when NEITHER source has seen the player lately.

    Our Elo's own answer stays authoritative for the ratings themselves --
    those are still computed from tennis-data.co.uk. This only overrides the
    question `is_stale` was asking, which is whether the player has been
    playing at all.
    """
    if not state.is_stale(player, today):
        return False
    if not recent:
        return True
    hit = resolve_name(player, names)
    if hit is None:
        return True
    return (today - pd.Timestamp(recent[hit])).days >= RECENT_DAYS


def orientation(ref_players, name_a, name_b):
    """True if ref_players[0] is name_a, False if it is name_b, None if that
    cannot be settled.

    None matters. The odds pair comes back ordered by the odds table's own
    spelling, which differs from the roster's, so it has to be matched by
    name. The old test was `resolve_name(ref_players[0], [a, b]) != b`, which
    reads a *failed* resolution as "first is a" and leaves the prices where
    they lie. On one card that gave Pegula her opponent's 5.30 instead of her
    own 1.15 -- a 95% favourite scored as a 19% outsider, in the model's
    input as well as on the page.
    """
    first = resolve_name(str(ref_players[0]), [name_a, name_b])
    second = resolve_name(str(ref_players[1]), [name_a, name_b])
    if first == name_a and second == name_b:
        return True
    if first == name_b and second == name_a:
        return False
    return None


def _sharp_reference(match_id):
    """((book, [odds_a, odds_b], players), context, books).

    The reference is the sharpest book quoting the match -- Pinnacle, then
    Betfair, then the lowest margin. `books` carries every plausibly priced
    two-way quote on the page, {bookmaker -> [odds_a, odds_b]} in the same
    player order as the reference, for the cross-book comparison. The
    context (round, qualifying flag, surface) rides along from the same page
    rather than costing a second request."""
    try:
        hist, context = te.fetch_match_detail(match_id)
    except Exception:
        return None, {}, {}
    if hist.empty:
        return None, context, {}
    cur = hist.sort_values("timestamp").groupby(["bookmaker", "player"]).last().reset_index()
    players = sorted(cur["player"].unique())
    if len(players) != 2:
        return None, context, {}

    def quotes(book):
        rows = [cur[(cur["bookmaker"] == book) & (cur["player"] == pl)] for pl in players]
        if any(len(r) == 0 for r in rows):
            return None
        return [float(r["odds"].iloc[0]) for r in rows]

    # A sharp book is preferred only while it is actually quoting the match:
    # Betfair carries 1.03/1.03 placeholders for unpriced draws, and taking
    # those on the strength of the book's name is worse than any soft price.
    books = {}
    for book in cur["bookmaker"].unique():
        q = quotes(book)
        if q and is_priced(q):
            books[str(book)] = q
    for book in SHARP_BOOKS:
        if book in books:
            return (book, books[book], players), context, books
    if not books:
        return None, context, {}
    best = min(books, key=lambda b: margin(books[b]))
    return (best, books[best], players), context, books


def circuit_of(tournament: str) -> str:
    name = str(tournament)
    if "itf" in name.lower():
        return "ITF"
    if CHALLENGER_MARKER in name.lower():
        return "Challenger"
    return "Tour"


PM_COLUMNS = ["venue", "tour", "tournament", "player_a", "player_b", "match_date",
              "bid_a", "ask_a", "bid_b", "ask_b", "liquidity", "volume",
              "fee_rate", "maker_fee_rate", "url"]


def fetch_prediction_markets(enabled: bool = True) -> tuple[pd.DataFrame, dict]:
    """Open singles moneylines from Polymarket and Kalshi, best-effort per
    venue: a feed being down must not stop the card from building."""
    frames, status = [], {}
    if not enabled:
        return pd.DataFrame(columns=PM_COLUMNS), status
    for name, fetch in (("Polymarket", polymarket.fetch_moneylines),
                        ("Kalshi", kalshi.fetch_moneylines)):
        try:
            df = fetch()
            frames.append(df.reindex(columns=PM_COLUMNS))
            status[name] = {"ok": True, "n_markets": int(len(df))}
        except Exception as exc:
            status[name] = {"ok": False, "n_markets": 0, "error": str(exc)[:200]}
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=PM_COLUMNS), status
    return pd.concat(frames, ignore_index=True), status


def refresh_schedule(days=(0, 1, 2)) -> pd.DataFrame:
    """Today plus two days from TennisExplorer into the processed CSV -- the
    same pages scripts/update_data.py fetches, so the card can be rebuilt on
    its own cadence without retraining anything."""
    frames = []
    for d in days:
        frames.append(te.fetch_matches(d))
        time.sleep(1.0)
    upcoming = pd.concat(frames, ignore_index=True).drop_duplicates(subset="match_id", keep="first")
    upcoming.to_csv(config.PROCESSED_DIR / "tennisexplorer_upcoming.csv", index=False)
    return upcoming


def load_stat_book(start_season: int | None = None):
    """Last-52-week serve/return profiles from TennisMyLife (Sackmann's
    schema, the statistics behind Tennis Abstract's player pages). Best
    effort: the card builds without it."""
    try:
        matches = tml.load_all(start_season=start_season or dt.date.today().year - 1)
        if matches.empty:
            return None
        return ps.StatBook(matches)
    except Exception as exc:
        print(f"Statistikprofile nicht verfuegbar: {exc}")
        return None


def fetch_ta_forecasts(enabled: bool = True) -> pd.DataFrame:
    """Tennis Abstract's own next-round probabilities for every event it is
    currently forecasting. Best effort."""
    if not enabled:
        return pd.DataFrame(columns=list(taf.COLUMNS))
    try:
        return taf.fetch_forecasts()
    except Exception as exc:
        print(f"Tennis-Abstract-Prognosen nicht verfuegbar: {exc}")
        return pd.DataFrame(columns=list(taf.COLUMNS))


def ta_forecast_for(forecasts: pd.DataFrame, name_1: str, name_2: str) -> dict | None:
    """Tennis Abstract's probability for the schedule pair, oriented onto it."""
    if forecasts is None or forecasts.empty:
        return None
    for r in forecasts.itertuples(index=False):
        orient = mc.pair_orientation(name_1, name_2, str(r.player_a), str(r.player_b))
        if orient is None or r.p_a is None or r.p_a != r.p_a:
            continue
        p_1 = float(r.p_a) if orient else 1.0 - float(r.p_a)
        h2h = (r.h2h_a, r.h2h_b) if orient else (r.h2h_b, r.h2h_a)
        return {"prob_1": round(p_1, 4), "round": r.round, "tournament": r.tournament,
                "h2h": [int(x) if x == x and x is not None else None for x in h2h],
                "url": r.url}
    return None


_STAT_KEYS = ("matches", "with_stats", "wins", "losses", "spw", "rpw", "ace_pct", "df_pct",
              "first_in", "first_won", "second_won", "hold_pct", "break_pct", "bp_saved",
              "bp_converted")


def stats_summary(book, name_1: str, name_2: str, surface: str, tour: str, best_of: int) -> dict | None:
    """Both players' profiles on this surface, the head-to-head, and the
    point-model forecast built from nothing but those numbers."""
    if book is None:
        return None
    full_1, full_2 = book.resolve(name_1), book.resolve(name_2)
    if not full_1 or not full_2 or full_1 == full_2:
        return None
    st_1, st_2 = book.stats(full_1, surface), book.stats(full_2, surface)
    if not st_1 or not st_2:
        return None
    tour_avg = book.tour_average(tour)
    sides = []
    for full, st in ((full_1, st_1), (full_2, st_2)):
        prof = st.get("surface") or st.get("overall") or {}
        side = {k: (round(prof[k], 4) if isinstance(prof.get(k), float) else prof.get(k))
                for k in _STAT_KEYS}
        side.update({"name": full, "scope": surface if st.get("surface") else "overall",
                     "form10": f'{st["form10"][0]}-{st["form10"][1]}', "rank": st.get("rank"),
                     "last_date": prof.get("last_date")})
        sides.append(side)
    prob = ps.stat_forecast(st_1, st_2, tour_avg, best_of)
    return {"sides": sides, "prob_1": round(prob, 4) if prob is not None else None,
            "tour_avg_spw": round(tour_avg, 4), "h2h": book.head_to_head(full_1, full_2)}


PRO_WALLETS = 20


def _slug_of(url) -> str | None:
    return str(url).rstrip("/").rsplit("/", 1)[-1] if url else None


def pro_positions(price_board: list[dict], max_wallets: int = PRO_WALLETS,
                  fetch=None) -> dict:
    """Open tennis positions of the best-ranked Polymarket wallets, each
    placed on the card where the match is on it: the side, the price the
    wallet paid, the price now, and the sharp fair value next to it.

    The ranking is scripts/update_pm_traders.py's (closing-line value over
    the last month, weekly). A position is information, not a tip: a
    market maker's position is inventory, and a wallet that beat the close
    last month can still be wrong on this match."""
    fetch = fetch or pt.positions
    try:
        lb = pd.read_csv(config.PROCESSED_DIR / "pm_tennis_traders.csv")
    except (OSError, ValueError):
        return {"leaderboard": [], "positions": [], "note": "noch keine Rangliste"}
    if "significant" in lb.columns:              # edges that survive the significance check
        lb = lb[lb["significant"].astype(bool)]
    if lb.empty:
        return {"leaderboard": [], "positions": [], "note": "Rangliste leer"}
    if "clv_net_mean" in lb.columns:             # CLV after fees where the ranking has it
        lb = lb.assign(clv_mean=lb["clv_net_mean"], clv_t=lb["clv_net_t"])
    by_slug = {}
    for e in price_board:
        for q in e.get("prediction_markets") or []:
            if q.get("venue") == "Polymarket" and _slug_of(q.get("url")):
                by_slug[_slug_of(q.get("url"))] = e
    rows = []
    for r in lb.head(max_wallets).itertuples(index=False):
        try:
            held = fetch(r.wallet)
        except Exception:
            continue
        for p in held:
            row = {"rank": int(r.rank), "name": r.name if isinstance(r.name, str) else "",
                   "wallet": r.wallet, "clv_mean": r.clv_mean, "clv_t": r.clv_t,
                   "slug": p["slug"], "title": p.get("title"), "outcome": p.get("outcome"),
                   "avg_price": p["avg_price"], "cur_price": p["cur_price"], "size": p["size"],
                   "initial_value": p.get("initial_value")}
            e = by_slug.get(p["slug"])
            idx = None
            if e:
                idx = next((i for i, pl in enumerate(e["players"])
                            if mc.name_matches(str(pl), str(p.get("outcome")))), None)
            if e and idx is not None:
                books = {b: q[idx] for b, q in (e.get("books") or {}).items()
                         if b not in mc.UNNAMED_VENUES and q and q[idx]}
                best = max(books, key=books.get) if books else None
                fair = e["fair"][idx]
                row.update({"match_id": e["match_id"], "date": e.get("date"),
                            "tournament": e["tournament"], "players": e["players"],
                            "side": e["players"][idx], "fair": fair,
                            "fair_source": e.get("fair_source", e["ref_book"]),
                            "fair_quality": e.get("fair_quality"),
                            "best_book": best, "best_odds": books.get(best) if best else None,
                            "ev_best": (round(fair * books[best] - 1, 4) if best else None)})
            rows.append(row)
        time.sleep(0.1)
    rows.sort(key=lambda x: (x.get("match_id") is None, x["rank"]))
    return {"leaderboard": lb.head(10).to_dict("records"), "positions": rows}


def _same_pair(ref_players, name_1, name_2):
    """Fast path for the price-only rows: the odds table usually spells the
    players exactly as the schedule does."""
    a, b = str(ref_players[0]).strip(), str(ref_players[1]).strip()
    if (a, b) == (name_1, name_2):
        return True
    if (a, b) == (name_2, name_1):
        return False
    return orientation(ref_players, name_1, name_2)


# ----------------------------------------------------------- every match ----
#
# The model table and the price board cover what can be scored or compared.
# The match list covers the rest as well: every singles match on today's and
# tomorrow's schedule (German dates), finished, running or still to come,
# ITF, UTR and the site's "Futures" band included. It costs no request of its
# own -- it joins what the run already read (schedule, match pages, model)
# with the weekly player table.

BERLIN = ZoneInfo("Europe/Berlin")
# Of the books TennisExplorer lists, the one BetInAsia brokers. SBOBET, ISN
# and Singbet are not on the page, and Betfair is not playable from Germany.
BETINASIA_BOOKS = ("Pinnacle",)
# Below this many matches on the surface, a player's overall 52-week line
# stands in for the surface line.
MIN_SURFACE_MATCHES = 5
_ELO_COLUMN = {"hard": "helo", "clay": "celo", "grass": "gelo"}


def category_of(tournament: str, url: str = "") -> str:
    name = str(tournament).lower()
    if "utr" in name:
        return "UTR"
    if "itf" in name or "futures" in name:
        return "ITF"
    if CHALLENGER_MARKER in name:
        return "Challenger"
    if "nationalliga" in name:
        return "Liga"
    return "WTA" if "-women/" in str(url) else "ATP"


class ProfileBook:
    """The weekly player table (player_profiles_{atp,wta}.csv), searchable by
    the schedule's `Lastname F.` spelling.

    resolve_name scans every candidate per call; indexing the table by each
    reading's surname first hands it only the players who could match, so a
    full schedule resolves in seconds rather than minutes."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.rows, self.index, self.matches, self.tour_avg = {}, {}, {}, {}
        for tour, df in frames.items():
            df = df.drop_duplicates("player").set_index("player", drop=False)
            self.rows[tour] = df
            self.matches[tour] = df["matches"].fillna(0).to_dict()
            idx: dict[str, list[str]] = {}
            for name in df.index:
                for surname, _ in _am.name_readings(str(name)):
                    idx.setdefault(surname, []).append(name)
            self.index[tour] = idx
            ok = df[df["matches_with_stats"].fillna(0) > 0]
            w = ok["matches_with_stats"]
            self.tour_avg[tour] = float((ok["spw"] * w).sum() / w.sum()) if len(ok) else 0.62

    @classmethod
    def load(cls, directory: Path | None = None) -> "ProfileBook":
        directory = Path(directory or config.PROCESSED_DIR)
        return cls({tour: pd.read_csv(directory / f"player_profiles_{tour}.csv")
                    for tour in ("atp", "wta")
                    if (directory / f"player_profiles_{tour}.csv").exists()})

    def resolve(self, query: str, tour: str):
        idx = self.index.get(tour) or {}
        cands = {c for surname, _ in _am.name_readings(str(query)) for c in idx.get(surname, ())}
        if not cands:
            return None
        hit = resolve_name(str(query), sorted(cands), weight=self.matches[tour].get)
        return self.rows[tour].loc[hit] if hit else None


def profile_side(row, surface: str | None) -> dict:
    """The player-table line the match list shows: ratings, the 52-week
    record and serve/return numbers -- on the match surface where the player
    has played at least MIN_SURFACE_MATCHES there, else overall."""
    def num(key, digits=3):
        v = row.get(key) if key else None
        return round(float(v), digits) if v is not None and pd.notna(v) else None

    surf = str(surface or "").lower()
    scope = surf if surf in _ELO_COLUMN and (num(f"{surf}_matches") or 0) >= MIN_SURFACE_MATCHES else None
    pre = f"{scope}_" if scope else ""
    form = row.get("form_last10")
    last = row.get("last_match")
    return {
        "name": str(row["player"]),
        "rank": num("official_rank", 0), "age": num("age", 1),
        "elo": num("elo", 0), "elo_rank": num("elo_rank", 0),
        "selo": num(_ELO_COLUMN.get(surf), 0), "yelo": num("yelo", 0),
        "w": num(f"{pre}wins", 0), "l": num(f"{pre}losses", 0),
        "n": num(f"{scope}_matches" if scope else "matches_with_stats", 0),
        "spw": num(f"{pre}spw"), "rpw": num(f"{pre}rpw"),
        "hold": num(f"{pre}hold_pct"), "brk": num(f"{pre}break_pct"),
        "scope": scope,
        "form": str(form) if pd.notna(form) else None,
        "last": str(last)[:10] if pd.notna(last) else None,
    }


def profile_forecasts(a: dict | None, b: dict | None, tour_avg: float, best_of: int) -> dict:
    """Two market-free opinions from the player table alone: Tennis
    Abstract's Elo (surface Elo when both players have one) and the
    Barnett-Clarke point model on the 52-week serve/return numbers, shrunk
    toward the tour average like player_stats.blended_rates."""
    out = {}
    if not a or not b:
        return out
    both_surface = a["selo"] is not None and b["selo"] is not None
    ra, rb = (a["selo"], b["selo"]) if both_surface else (a["elo"], b["elo"])
    if ra is not None and rb is not None:
        out["elo"] = round(_ta_elo_probability(ra, rb), 4)
        out["elo_basis"] = "surface" if both_surface else "overall"
    if None not in (a["spw"], a["rpw"], b["spw"], b["rpw"]):
        def blend(side):
            n = side["n"] or 0
            w = n / (n + ps.SHRINK_MATCHES)
            return (w * side["spw"] + (1 - w) * tour_avg,
                    w * side["rpw"] + (1 - w) * (1.0 - tour_avg))
        (sa, ra_), (sb, rb_) = blend(a), blend(b)
        p, q = ps.point_probabilities(sa, ra_, sb, rb_, tour_avg)
        out["stat"] = round(ps.match_probability(round(p, 4), round(q, 4), best_of), 4)
    return out


def _compact(value):
    """Drops empty fields: most of the list is ITF and UTR matches with no
    profile, model or book, and their nulls would be most of the payload."""
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items()
                if v is not None and v != [] and v != [None, None]}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    return value


def _score_text(m) -> str | None:
    sets = [m.get("sets_won1"), m.get("sets_won2")]
    out = f"{int(sets[0])}:{int(sets[1])}" if all(pd.notna(s) for s in sets) else ""
    if isinstance(m.get("score"), str) and m["score"].strip():
        out = f"{out} ({m['score'].strip()})" if out else m["score"].strip()
    return out or None


def all_matches_board(sched: pd.DataFrame, price_board: list[dict], matches: list[dict],
                      profiles: ProfileBook, threshold: float, surface_of=None,
                      now=None, days: int = 2) -> dict:
    """Every singles match of today and tomorrow (Berlin dates), each with
    the player table, the market, every forecast this run has, and the
    verdict for a BetInAsia bettor.

    A signal is the model table's own signal (trained model, not stale,
    sharp reference, EV past the threshold) priced at a BetInAsia book. Elo
    and point-model gaps are shown, never signalled -- the same rule as the
    model table, for the reasons given there."""
    now = pd.Timestamp(now or pd.Timestamp.now(tz="UTC")).tz_convert("UTC")
    first = now.tz_convert(BERLIN).date()
    wanted = [(first + dt.timedelta(days=i)).isoformat() for i in range(days)]
    by_id = {str(e["match_id"]): e for e in price_board}
    scored = {str(m["match_id"]): m for m in matches}
    starts = start_times(sched)
    done = ~unplayed_mask(sched)
    running = started_mask(sched, now)

    rows = []
    for i, m in sched.iterrows():
        p1, p2 = str(m["player1"]), str(m["player2"])
        if "/" in p1 or "/" in p2:
            continue
        st = starts.loc[i]
        day = st.tz_convert(BERLIN).date().isoformat() if pd.notna(st) else str(m.get("date"))
        if day not in wanted:
            continue
        mid = str(m["match_id"])
        url = str(m.get("tournament_url", ""))
        # The site's collective "Futures" band carries no tournament link, so
        # no tour either: such a player is looked up in both tables and kept
        # only when exactly one of them knows the name.
        tours = ["wta"] if "-women/" in url else ["atp"] if "-men/" in url else ["atp", "wta"]
        tour = tours[0]
        entry, sc = by_id.get(mid) or {}, scored.get(mid) or {}
        surface = entry.get("surface") or (surface_of(str(m["tournament"])) if surface_of else None)
        best_of = entry.get("best_of") or best_of_for(str(m["tournament"]), tour)

        sides, found = [], set()
        for name in (p1, p2):
            hits = [(t, r) for t in tours if (r := profiles.resolve(name, t)) is not None]
            sides.append(profile_side(hits[0][1], surface) if len(hits) == 1 else None)
            found.update(t for t, _ in hits[:1] if len(hits) == 1)
        if len(found) == 1:
            tour = found.pop()
        elif found:
            sides = [None, None]
        if sides[0] and sides[1] and sides[0]["name"] == sides[1]["name"]:
            sides = [None, None]
        fc = profile_forecasts(sides[0], sides[1], profiles.tour_avg.get(tour, 0.62), best_of)

        odds = ([round(float(m["odds1"]), 3), round(float(m["odds2"]), 3)]
                if pd.notna(m.get("odds1")) and pd.notna(m.get("odds2")) else None)
        books = {b: q for b, q in (entry.get("books") or {}).items() if b != "TennisExplorer"}
        if entry:
            fair, fair_source, quality = entry["fair"], entry["fair_source"], entry["fair_quality"]
        elif odds and is_priced(odds):
            fair = [round(x, 4) for x in odds_math.shin_devig(odds)]
            fair_source, quality = "TennisExplorer", "soft"
        else:
            fair, fair_source, quality = None, None, None
        pin = next((list(books[b]) for b in BETINASIA_BOOKS if b in books), None)
        best = None
        if books:
            best = [max(((b, q[k]) for b, q in books.items()), key=lambda t: t[1]) for k in (0, 1)]
            best = [[b, round(o, 3)] for b, o in best]

        model_p = entry.get("model_prob_1")
        ev_bia = ([round(model_p * pin[0] - 1, 4), round((1 - model_p) * pin[1] - 1, 4)]
                  if model_p is not None and pin else None)
        signal = None
        if sc.get("signal") and sc.get("ref_book") in BETINASIA_BOOKS:
            k = max((0, 1), key=lambda j: sc["sides"][j]["ev_at_ref"])
            signal = {"side": k, "book": sc["ref_book"], "odds": sc["sides"][k]["ref_odds"],
                      "ev": sc["sides"][k]["ev_at_ref"]}
        # A soft book paying more than the sharp (or liquid exchange) fair
        # value: real EV, but at a book BetInAsia does not carry -- shown as
        # a hint, never as a signal.
        soft = None
        if quality in ("sharp", "exchange"):
            cands = [v for v in entry.get("values") or []
                     if v["kind"] == "book" and not v["is_sharp"] and not v["signal_only"]
                     and v["venue"] not in BETINASIA_BOOKS and v["ev"] is not None
                     and v["ev"] >= threshold]
            if cands:
                v = max(cands, key=lambda r: r["ev"])
                soft = {"side": 0 if v["player"] == entry["players"][0] else 1,
                        "book": v["venue"], "odds": v["odds"], "ev": v["ev"]}

        status = "finished" if done.loc[i] else ("live" if running.loc[i] else "upcoming")
        h2h = (entry.get("stats") or {}).get("h2h")
        rows.append({
            "id": mid, "day": day,
            "time": st.tz_convert(BERLIN).strftime("%H:%M") if pd.notna(st) else None,
            "tournament": str(m["tournament"]), "cat": category_of(m["tournament"], url),
            "tour": tour, "surface": surface, "best_of": best_of, "round": entry.get("round"),
            "status": status, "score": _score_text(m) if status != "upcoming" else None,
            "players": [p1, p2], "profiles": sides, "odds": odds,
            "fair": fair, "fair_source": fair_source, "fair_quality": quality,
            "pinnacle": pin, "best": best,
            "model": model_p, "method": sc.get("method") or entry.get("method"),
            "stale": sc.get("stale_players") or [],
            "elo": fc.get("elo"), "elo_basis": fc.get("elo_basis"), "stat": fc.get("stat"),
            "ta_forecast": (entry.get("ta_forecast") or {}).get("prob_1"),
            "h2h": [h2h["wins_a"], h2h["wins_b"]] if h2h else None,
            "ev_bia": ev_bia, "signal": signal, "soft": soft,
        })

    cat_rank = {c: k for k, c in enumerate(("ATP", "WTA", "Challenger", "ITF", "UTR", "Liga"))}
    rows.sort(key=lambda r: (r["day"], cat_rank.get(r["cat"], 9), r["tournament"],
                             r["time"] or "99:99", r["players"][0]))
    summary = []
    for d in wanted:
        sub = [r for r in rows if r["day"] == d]
        summary.append({
            "date": d, "n": len(sub),
            "n_upcoming": sum(r["status"] == "upcoming" for r in sub),
            "n_profiled": sum(1 for r in sub if r["profiles"][0] and r["profiles"][1]),
            "n_model": sum(r["model"] is not None for r in sub),
            "n_pinnacle": sum(r["pinnacle"] is not None for r in sub),
            "n_signals": sum(r["signal"] is not None for r in sub),
        })
    return {"days": summary, "matches": [_compact(r) for r in rows], "threshold": threshold,
            "books": list(BETINASIA_BOOKS), "n_signals": sum(s["n_signals"] for s in summary)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", type=Path, default=config.PROCESSED_DIR / "dashboard.json")
    ap.add_argument("--limit", type=int, default=200,
                    help="max tour/challenger matches; each costs one odds-history request (~2-4s)")
    ap.add_argument("--tour", choices=("atp", "wta", "both"), default="both")
    ap.add_argument("--no-challenger", action="store_true")
    ap.add_argument("--date", action="append", metavar="YYYY-MM-DD",
                    help="restrict to these playing days; repeatable")
    ap.add_argument("--threshold", type=float, default=DEFAULT_EDGE_THRESHOLD,
                    help="minimum EV on the backed side (0.05 = +5%%)")
    ap.add_argument("--refresh-schedule", action="store_true",
                    help="fetch today and the next two days from TennisExplorer first")
    ap.add_argument("--no-prediction-markets", action="store_true",
                    help="skip Polymarket and Kalshi")
    ap.add_argument("--itf-limit", type=int, default=40,
                    help="ITF matches to add to the price board when a prediction market "
                         "quotes them (the model never scores ITF); each costs one request")
    ap.add_argument("--no-snapshots", action="store_true",
                    help="do not append this run's quotes to odds_snapshots.csv / picks_log.csv")
    ap.add_argument("--no-ta-forecasts", action="store_true",
                    help="skip Tennis Abstract's tournament forecast pages")
    ap.add_argument("--no-stats", action="store_true",
                    help="skip the TennisMyLife serve/return profiles and the point model")
    ap.add_argument("--no-pm-pros", action="store_true",
                    help="skip the open positions of the ranked Polymarket tennis wallets")
    args = ap.parse_args()

    if args.refresh_schedule:
        refresh_schedule()

    sched = pd.read_csv(config.PROCESSED_DIR / "tennisexplorer_upcoming.csv",
                        dtype={"match_id": str})
    sched_all = sched.copy()
    # ITF stays in for the price board; the model filter is applied further
    # down. The remaining exclusions are events no venue prices seriously.
    sched = sched[~sched["tournament"].str.contains(PRICE_BOARD_EXCLUDE, na=False,
                                                     regex=True, case=False)]
    sched = sched[sched["odds1"].notna() & sched["odds2"].notna()]
    n_finished = int((~unplayed_mask(sched)).sum())
    sched = sched[unplayed_mask(sched)]
    now = pd.Timestamp.now(tz="UTC")
    n_in_play = int(started_mask(sched, now).sum())
    sched = sched[~started_mask(sched, now)]
    sched = sched.assign(start_time=start_times(sched))
    if args.date:
        if "date" not in sched.columns:
            raise SystemExit("Der Spielplan hat keine date-Spalte -- "
                             "bitte zuerst scripts/update_data.py neu laufen lassen.")
        sched = sched[sched["date"].isin(args.date)]
    if args.tour in ("atp", "wta"):
        suffix = "-men/" if args.tour == "atp" else "-women/"
        sched = sched[sched["tournament_url"].str.contains(suffix, regex=False, na=False)]

    is_itf = sched["tournament"].str.contains("ITF", case=False, na=False)
    core = sched[~is_itf & ~sched["tournament"].str.contains(EXCLUDE_EVENTS, na=False,
                                                              regex=True, case=False)]
    if args.no_challenger:
        core = core[~core["tournament"].str.contains(CHALLENGER_MARKER, case=False, na=False)]
    is_ch = core["tournament"].str.contains(CHALLENGER_MARKER, case=False, na=False)
    core = (core.assign(_tier=is_ch.astype(int))
                .sort_values("_tier", kind="stable")
                .drop(columns="_tier")
                .head(args.limit))

    # Prediction markets first: they decide which ITF matches are worth a
    # request. Polymarket and Kalshi both list ITF singles down to M15/W15,
    # which is where the model has nothing to say but a price board still can.
    pm_all, pm_status = fetch_prediction_markets(not args.no_prediction_markets)
    pm_hits = mc.attach_markets(sched, pm_all)
    itf_extra = sched[is_itf & sched["match_id"].astype(str).isin(set(pm_hits))].head(args.itf_limit)
    todo = pd.concat([core.assign(_price_only=False), itf_extra.assign(_price_only=True)],
                     ignore_index=True)

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

    def ta_side(query: str, surface: str) -> dict | None:
        """Tennis Abstract's full line for a player: overall and surface Elo,
        peak, official rank and age -- shown for every match, not only the
        ones the model cannot score."""
        hit = resolve_name(query, ta_names)
        if not hit:
            return None
        row = ta_by_name.loc[hit]
        col = TA_SURFACE_COLUMN.get(surface.lower())

        def num(key):
            v = row.get(key) if key else None
            return float(v) if v is not None and pd.notna(v) else None

        return {"name": hit, "elo": num("elo"), "surface_elo": num(col), "surface": surface,
                "peak_elo": num("peak_elo"), "official_rank": num("official_rank"),
                "age": num("age"), "elo_rank": num("elo_rank")}

    def ta_block(name_1: str, name_2: str, surface: str) -> dict | None:
        a, b = ta_side(name_1, surface), ta_side(name_2, surface)
        if not a or not b or a["name"] == b["name"]:
            return None
        ra = a["surface_elo"] if a["surface_elo"] is not None else a["elo"]
        rb = b["surface_elo"] if b["surface_elo"] is not None else b["elo"]
        if ra is None or rb is None:
            return None
        return {"sides": [a, b], "prob_1": round(_ta_elo_probability(ra, rb), 4),
                "basis": "surface" if (a["surface_elo"] is not None and b["surface_elo"] is not None)
                else "overall"}

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

    ta_fc = fetch_ta_forecasts(not args.no_ta_forecasts)
    book = None if args.no_stats else load_stat_book()

    today = pd.Timestamp.now().normalize()
    recent_play = load_recent_play()
    recent_names = list(recent_play)
    matches, skipped, price_board = [], [], []
    for _, m in todo.iterrows():
        match_id = str(m["match_id"])
        label = f"{m['player1']} vs {m['player2']}"
        price_only = bool(m["_price_only"])
        tour = "wta" if "-women/" in str(m["tournament_url"]) else "atp"
        circuit = circuit_of(m["tournament"])

        a = b = None
        thin_reason = None
        if not price_only:
            a = resolve_name(str(m["player1"]), roster, weight=played.get)
            b = resolve_name(str(m["player2"]), roster, weight=played.get)
            if not a or not b or a == b:
                thin_reason = "Spieler nicht in unserer Historie"
            elif min(played.get(a, 0), played.get(b, 0)) < MIN_MATCHES_PLAYED:
                thin = a if played.get(a, 0) < played.get(b, 0) else b
                thin_reason = f"{thin}: nur {played.get(thin, 0):.0f} Matches bei uns"

            # Our own Elo is too thin -- fall back to Tennis Abstract's rating if
            # it covers both players, rather than dropping the match. Whether they
            # are in their table is a name question, settled here so a match we
            # cannot score either way never costs a match-detail request; which
            # rating to read is a surface question, settled once the page is in.
            if thin_reason and not (resolve_name(str(m["player1"]), ta_names)
                                    and resolve_name(str(m["player2"]), ta_names)):
                skipped.append({"match": label, "tournament": str(m["tournament"]),
                                "reason": thin_reason + " und kein Tennis-Abstract-Elo"})
                continue

        ref, context, books = _sharp_reference(match_id)
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

        # The match page states the surface outright; the tournament-name
        # lookup is only a fallback for a match whose page we could not read.
        # It had Augsburg on hard court, which is a clay challenger.
        surface = (normalize_surface(context.get("surface"))
                   or court_surface(str(m["tournament"])))
        best_of = best_of_for(str(m["tournament"]), tour,
                              is_qualifying=bool(context.get("is_qualifying")))
        speed = tourney_matching.lookup_surface_speed(
            speed_index, dt.date.today().year, str(m["tournament"]))

        ta_fallback = None
        if thin_reason:
            ra = ta_rating(str(m["player1"]), surface)
            rb = ta_rating(str(m["player2"]), surface)
            if not (ra and rb):
                skipped.append({"match": label, "tournament": str(m["tournament"]),
                                "reason": thin_reason + " und kein Tennis-Abstract-Elo"})
                continue
            ta_fallback = (ra, rb)

        stale = []
        p_a = None
        if price_only:
            method, label_a, label_b = "price_only", str(m["player1"]), str(m["player2"])
            elos, counts = (None, None), (None, None)
            first_is_a = _same_pair(ref_players, label_a, label_b)
        elif ta_fallback:
            (name_a, elo_a), (name_b, elo_b) = ta_fallback
            method, label_a, label_b = "ta_elo", name_a, name_b
            elos = (elo_a, elo_b)
            counts = (None, None)
            p_a = _ta_elo_probability(elo_a, elo_b)
            first_is_a = orientation(ref_players, name_a, name_b)
        else:
            method, label_a, label_b = "model", a, b
            elos = (float(elo_overall.get(a, float("nan"))),
                    float(elo_overall.get(b, float("nan"))))
            counts = (int(played.get(a, 0)), int(played.get(b, 0)))
            first_is_a = orientation(ref_players, a, b)
            stale = [p for p in (a, b)
                     if still_stale(p, state, today, recent_play, recent_names)]

        # Orient the reference prices onto (first player, second player).
        # When the pair cannot be matched by name, fall back to the schedule
        # row, whose two odds columns are already in player1/player2 order --
        # a correct soft price beats a sharp one on the wrong player. The
        # other books on the page share the reference's order, so they are
        # flipped with it, or dropped with it when it cannot be settled.
        if first_is_a is None:
            ref_book = "TennisExplorer"
            ref_odds = [float(m["odds1"]), float(m["odds2"])]
            books = {}
            if not is_priced(ref_odds):
                skipped.append({"match": label, "tournament": str(m["tournament"]),
                                "reason": "Quoten nicht eindeutig einem Spieler zuzuordnen"})
                continue
        elif not first_is_a:
            ref_odds = [ref_odds[1], ref_odds[0]]
            books = {book: [q[1], q[0]] for book, q in books.items()}
        if not books:
            books = {ref_book: list(ref_odds)}

        # Every other venue's price on the same pair, in the same order. A
        # market whose own start time has passed is trading in-play and is
        # left out: its price answers a different question by then.
        players = (label_a, label_b)
        pm_quotes = [mc.market_quote(r, r["first_is_player1"]) for r in pm_hits.get(match_id, [])]
        pm_quotes = [q for q in pm_quotes if q.get("start_time") is None or q["start_time"] > now]

        # The fair value and the reference *price* are two different things.
        # The price is what a book offers and what EV is computed at; the fair
        # value is the best estimate of the true probability. A sharp book
        # gives both. Without one, a liquid prediction-market mid is a better
        # fair value than a soft book's de-vigged price (see
        # market_compare.exchange_anchor), while the soft price stays the
        # quote the model table shows.
        fair_a, fair_b = odds_math.shin_devig(ref_odds)
        fair_source = ref_book
        fair_quality = "sharp" if ref_book in SHARP_BOOKS else "soft"
        if fair_quality != "sharp":
            anchor = mc.exchange_anchor(pm_quotes)
            if anchor:
                fair_a, fair_b = anchor["fair"]
                fair_source, fair_quality = f"{anchor['venue']} Mid", "exchange"

        if method == "model":
            # Averaged over both orderings of the pair: the raw classifier is
            # not antisymmetric, and on this card the ordering moved the
            # answer by more than the edge being measured.
            p_a = matchup_probability(model, state, a, b, surface, best_of,
                                       market_prob_a=fair_a, surface_speed=speed)

        values = mc.value_rows(players, (fair_a, fair_b), books, pm_quotes, ref_book)
        arb = mc.best_arbitrage(players, books, pm_quotes)

        # Three more opinions on the same pair, each from a different source
        # and none of them fed by the market: Tennis Abstract's Elo (overall
        # and surface) for both players, Tennis Abstract's own tournament
        # forecast where the event is on its site, and a point model from
        # the players' last-52-week serve and return numbers.
        ta = ta_block(str(m["player1"]), str(m["player2"]), surface)
        ta_fcst = ta_forecast_for(ta_fc, str(m["player1"]), str(m["player2"]))
        stats = stats_summary(book, str(m["player1"]), str(m["player2"]), surface, tour, best_of)
        entry = {
            "match_id": match_id,
            "date": str(m["date"]) if pd.notna(m.get("date")) else None,
            "start_time": (m["start_time"].isoformat(timespec="minutes")
                           if pd.notna(m.get("start_time")) else None),
            "tournament": str(m["tournament"]),
            "tour": tour,
            "circuit": circuit,
            "round": context.get("round"),
            "method": method,
            "players": list(players),
            "ref_book": ref_book,
            "ref_is_sharp": ref_book in SHARP_BOOKS,
            "fair_source": fair_source,
            "fair_quality": fair_quality,
            "fair": [round(fair_a, 4), round(fair_b, 4)],
            "books": books,
            "prediction_markets": pm_quotes,
            "values": values,
            "arb": arb,
            "best_of": best_of,
            "surface": surface,
            "ta": ta,
            "ta_forecast": ta_fcst,
            "stats": stats,
            "model_prob_1": None,
        }
        price_board.append(entry)
        if price_only:
            continue

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
            "match_id": match_id,
            "date": entry["date"],
            "tournament": str(m["tournament"]),
            "tour": tour,
            "circuit": circuit,
            "surface": surface,
            "best_of": best_of,
            "round": context.get("round"),
            "is_qualifying": bool(context.get("is_qualifying")),
            "ref_book": ref_book,
            "ref_margin": round(margin(ref_odds), 4),
            "fair_source": fair_source,
            "fair_quality": fair_quality,
            # "model" = our trained classifier with the market price blended in.
            # "ta_elo" = Tennis Abstract's rating through their published Elo
            # formula, no market input. Never mix the two in one comparison.
            "method": method,
            "sides": sides,
            # Players whose last match in our feed is old enough that their
            # rest/form/fatigue features describe the gap, not the player.
            "stale_players": stale,
            "best_edge": round(max(s["edge"] for s in sides), 4),
            "best_ev": round(max(s["ev_at_ref"] for s in sides), 4),
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
            # The market feature the model was trained on is Pinnacle's
            # de-vigged price, and training drops every row without one. A
            # soft book's de-vigged price is an unbiased but noisier stand-in:
            # measured over 20 000 historical matches carrying both, the two
            # differ by 0.63 percentage points at the median and 1.69 at the
            # 90th percentile, with a median bias of +0.07. That noise is the
            # size of the edge being measured, so a row priced only by a soft
            # book is shown but is not called a signal.
            "ref_is_sharp": ref_book in SHARP_BOOKS,
            # Thresholded on EV, not edge. The brief is "bet at +5% EV", and
            # the two are not the same test: edge is (forecast - market),
            # which is an exact mirror between the two sides, while EV is
            # edge converted at that side's own price. Mannarino at 3.85
            # carries +5.23% EV on a 3.41 point edge; a 3.41 point edge on a
            # 1.30 shot is worth +1.1%. Thresholding on edge therefore
            # demanded far more from a longshot than from a favourite.
            "signal": (method == "model" and not stale
                       and ref_book in SHARP_BOOKS
                       and max(s["ev_at_ref"] for s in sides) > args.threshold),
            "books": books,
            "prediction_markets": pm_quotes,
            "arb": arb,
            "ta": ta,
            "ta_forecast": ta_fcst,
            "stats": stats,
        })
        if method == "model":
            entry["model_prob_1"] = round(p_a, 4)

    matches.sort(key=lambda x: x["best_edge"], reverse=True)
    boards = build_boards(price_board)
    pros = ({"leaderboard": [], "positions": [], "note": "abgeschaltet"} if args.no_pm_pros
            else pro_positions(price_board))
    try:
        sharpness = json.loads((config.REPORTS_DIR / "prediction_market_sharpness.json").read_text())
        sharpness.pop("leader_preview", None)
    except (OSError, ValueError):
        sharpness = {}
    every = all_matches_board(
        sched_all, price_board, matches, ProfileBook.load(), args.threshold,
        surface_of=lambda t: surface_by_name.get(tourney_matching.normalize_tourney_name(t)))
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    payload = {
        "generated_at": generated_at,
        "threshold": args.threshold,
        "n_scheduled": int(len(sched)),
        "n_finished": n_finished,
        "n_in_play": n_in_play,
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
        "audit": audit_numbers(),
        # Price comparison across venues, model or no model.
        "price_board": price_board,
        "prediction_markets": {
            "status": pm_status,
            "n_markets": int(len(pm_all)),
            "n_matched": len(pm_hits),
            "n_itf_added": int(len(itf_extra)),
        },
        "sources": {
            "ta_elo": sum(1 for e in price_board if e.get("ta")),
            "ta_forecast": sum(1 for e in price_board if e.get("ta_forecast")),
            "ta_forecast_pairings": int(len(ta_fc)),
            "stats": sum(1 for e in price_board if e.get("stats")),
            "stats_players": len(book.players) if book is not None else 0,
        },
        **boards,
        "pm_pros": pros,
        "pm_sharpness": sharpness,
        "all_matches": every,
    }
    args.out.write_text(json.dumps(payload, indent=1, default=str))
    if not args.no_snapshots:
        n_snap = record_snapshots(price_board, matches, generated_at, pros)
        print(f"{n_snap} Quoten-Snapshots angehaengt")
    print(f"{payload['n_scored']} Partien bewertet, {payload['n_signals']} Signale, "
          f"{len(skipped)} uebersprungen, {n_finished} bereits gespielt, "
          f"{n_in_play} laufen gerade -> {args.out}")
    print(f"Preisvergleich: {len(price_board)} Partien, {len(boards['soft_value'])} Soft-Value-Seiten, "
          f"{len(boards['pm_board'])} Prediction-Market-Seiten, {len(boards['arbs'])} Arbitragen "
          f"({payload['prediction_markets']['n_matched']} Partien mit Polymarket/Kalshi-Preis, "
          f"{payload['prediction_markets']['n_itf_added']} ITF dazu)")
    print("Referenzbuecher:", payload["ref_books"])
    print("Alle Partien:", ", ".join(
        f"{d['date']} {d['n']} ({d['n_upcoming']} offen, {d['n_profiled']} mit Profil, "
        f"{d['n_model']} Modell, {d['n_pinnacle']} Pinnacle, {d['n_signals']} Signale)"
        for d in every["days"]))


def build_boards(price_board: list[dict]) -> dict:
    """The three cross-venue tables, flattened and sorted for the page.

    Only matches with a sharp or exchange-grade fair value enter the EV
    tables: against a soft reference the "fair" value is itself a soft
    price, and a 1-2% gap between two soft books is noise."""
    soft, pm, arbs, near = [], [], [], []
    for e in price_board:
        ctx = {"match_id": e["match_id"], "date": e["date"], "tournament": e["tournament"],
               "circuit": e["circuit"], "tour": e["tour"], "round": e.get("round"),
               "players": e["players"], "ref_book": e["ref_book"],
               "ref_is_sharp": e["ref_is_sharp"],
               "fair_source": e.get("fair_source", e["ref_book"]),
               "fair_quality": e.get("fair_quality", "sharp" if e["ref_is_sharp"] else "soft")}
        if ctx["fair_quality"] in ("sharp", "exchange"):
            for v in e["values"]:
                if v["kind"] == "book" and not v["is_sharp"] and v["ev"] is not None and v["ev"] > 0:
                    soft.append({**ctx, **v})
                elif v["kind"] == "prediction":
                    pm.append({**ctx, **v})
        arb = e.get("arb")
        if arb:
            row = {**ctx, **arb}
            if arb["is_arbitrage"]:
                arbs.append(row)
            else:
                near.append(row)
    soft.sort(key=lambda r: r["ev"], reverse=True)
    pm.sort(key=lambda r: (r["ev"] if r["ev"] is not None else -1), reverse=True)
    arbs.sort(key=lambda r: r["profit"], reverse=True)
    # The closest misses, so a card without an arbitrage still says how far
    # off the best pair was.
    near = sorted(near, key=lambda r: r["margin"])[:8]
    return {"soft_value": soft, "pm_board": pm, "arbs": arbs, "near_arbs": near}


PICK_COLUMNS = ["taken_at", "match_id", "date", "tournament", "player", "venue", "kind",
                "source", "odds", "fair_prob", "ev", "ref_book"]
FORECAST_COLUMNS = ["taken_at", "match_id", "date", "tournament", "circuit", "player1", "player2",
                    "surface", "best_of", "market_fair_1", "fair_source", "model_1", "ta_elo_1",
                    "ta_forecast_1", "stats_1"]


def forecast_rows(price_board: list[dict], taken_at: str) -> list[dict]:
    """One row per match with every source's probability for player 1 --
    the record that lets a later run score market, model, Tennis Abstract
    and the point model against the results on equal terms."""
    rows = []
    for e in price_board:
        ta, fc, st = e.get("ta"), e.get("ta_forecast"), e.get("stats")
        if not (ta or fc or st or e.get("model_prob_1") is not None):
            continue
        rows.append({
            "taken_at": taken_at, "match_id": e["match_id"], "date": e["date"],
            "tournament": e["tournament"], "circuit": e["circuit"],
            "player1": e["players"][0], "player2": e["players"][1],
            "surface": e.get("surface"), "best_of": e.get("best_of"),
            "market_fair_1": e["fair"][0], "fair_source": e.get("fair_source"),
            "model_1": e.get("model_prob_1"),
            "ta_elo_1": ta["prob_1"] if ta else None,
            "ta_forecast_1": fc["prob_1"] if fc else None,
            "stats_1": st["prob_1"] if st else None,
        })
    return rows


GAP_COLUMNS = ["taken_at", "match_id", "date", "tournament", "circuit", "player", "venue", "mid",
               "fair", "fair_source", "spread", "liquidity"]
PRO_COLUMNS = ["taken_at", "rank", "name", "wallet", "clv_mean", "clv_t", "slug", "title", "outcome",
               "avg_price", "cur_price", "size", "match_id", "side", "fair", "fair_source",
               "best_book", "best_odds", "ev_best"]


def _append(path, rows, columns) -> None:
    if not rows:
        return
    header = not path.exists() or path.stat().st_size == 0
    pd.DataFrame(rows, columns=columns).to_csv(path, mode="a", header=header, index=False)


def gap_rows(price_board: list[dict], taken_at: str) -> list[dict]:
    """Prediction-market mids next to a sharp book's fair value -- the
    running record behind the 'how sharp are they' measurement."""
    rows = []
    for e in price_board:
        if e.get("fair_quality") != "sharp":
            continue
        for q in e.get("prediction_markets") or []:
            for i in range(2):
                if q["mid"][i] is None:
                    continue
                spread = (q["ask"][i] - q["bid"][i]) if None not in (q["ask"][i], q["bid"][i]) else None
                rows.append({"taken_at": taken_at, "match_id": e["match_id"], "date": e["date"],
                             "tournament": e["tournament"], "circuit": e["circuit"],
                             "player": e["players"][i], "venue": q["venue"],
                             "mid": round(q["mid"][i], 4), "fair": e["fair"][i],
                             "fair_source": e.get("fair_source"),
                             "spread": round(spread, 4) if spread is not None else None,
                             "liquidity": q.get("liquidity")})
    return rows


def record_snapshots(price_board: list[dict], matches: list[dict], taken_at: str,
                     pros: dict | None = None) -> int:
    """Append this run's quotes and its positive-EV sides to the two logs
    that make opening-vs-closing and closing-line-value measurable later.
    Nothing here is a bet; it is the record against which one would be judged."""
    rows = []
    for e in price_board:
        rows.extend(mc.snapshot_rows(e, taken_at))
    n = mc.append_snapshots(config.PROCESSED_DIR / "odds_snapshots.csv", rows)

    picks = []
    for e in price_board:
        if e.get("fair_quality", "sharp" if e["ref_is_sharp"] else "soft") not in ("sharp", "exchange"):
            continue
        for v in e["values"]:
            if v.get("ev") is not None and v["ev"] > 0 and not v.get("is_reference"):
                picks.append({"taken_at": taken_at, "match_id": e["match_id"], "date": e["date"],
                              "tournament": e["tournament"], "player": v["player"],
                              "venue": v["venue"], "kind": v["kind"], "source": "value",
                              "odds": v["odds"], "fair_prob": v["fair_prob"], "ev": v["ev"],
                              "ref_book": e.get("fair_source", e["ref_book"])})
    for m in matches:
        if m["signal"]:
            s = max(m["sides"], key=lambda x: x["ev_at_ref"])
            picks.append({"taken_at": taken_at, "match_id": m["match_id"], "date": m["date"],
                          "tournament": m["tournament"], "player": s["player"],
                          "venue": m["ref_book"], "kind": "model", "source": "model_signal",
                          "odds": s["ref_odds"], "fair_prob": s["market_prob"],
                          "ev": s["ev_at_ref"], "ref_book": m["ref_book"]})
    if picks:
        path = config.PROCESSED_DIR / "picks_log.csv"
        header = not path.exists() or path.stat().st_size == 0
        pd.DataFrame(picks, columns=PICK_COLUMNS).to_csv(path, mode="a", header=header, index=False)
    _append(config.PROCESSED_DIR / "pm_gap_log.csv", gap_rows(price_board, taken_at), GAP_COLUMNS)
    _append(config.PROCESSED_DIR / "pm_pro_positions_log.csv",
            [{**r, "taken_at": taken_at} for r in (pros or {}).get("positions", [])], PRO_COLUMNS)
    fc_rows = forecast_rows(price_board, taken_at)
    if fc_rows:
        path = config.PROCESSED_DIR / "forecasts_log.csv"
        header = not path.exists() or path.stat().st_size == 0
        pd.DataFrame(fc_rows, columns=FORECAST_COLUMNS).to_csv(path, mode="a", header=header, index=False)
    return n


if __name__ == "__main__":
    main()
