"""Every ATP and WTA player in one table, refreshed every Tuesday.

Per player:

- Tennis Abstract Elo (reports/*_elo_ratings.html): Elo and its rank,
  hard/clay/grass Elo with their ranks, peak Elo and its month, official
  ranking, age.
- Tennis Abstract season Elo (reports/*_season_yelo_ratings.html): yElo,
  its rank, wins and losses this calendar year.
- The last 52 weeks of match statistics, overall and on hard, clay and
  grass: matches, wins, losses, serve points won, return points won, total
  points won, dominance ratio, aces, double faults, first serve in and won,
  second serve won, hold, break, break points saved and converted, aces
  conceded. These are the numbers behind Tennis Abstract's player pages;
  they are read from TennisMyLife, which publishes the same (Sackmann)
  schema, because the site's own per-player logs sit under paths its
  robots.txt disallows (/jsfrags/, /jsmatches/, /jsplayers/).

Players are the union of both sources. Tennis Abstract rates players with
recent results down to ITF $50K+; TennisMyLife covers everyone with a
main-tour, challenger or ATP-qualifying match in the window, and for the
WTA the main tour only -- it carries no WTA 125 or ITF matches. A player
found in one source only has the other source's columns empty.

Outputs, all under data/processed/:

    player_profiles_atp.csv, player_profiles_wta.csv   the tables
    player_profiles_meta.json                           dates, counts, errors
    ta_elo_current.csv, ta_elo_{atp,wta}_general.csv    Tennis Abstract Elo
    ta_yelo_current.csv                                 Tennis Abstract yElo
    ta_elo_history.csv                                  one snapshot per TA update
    ta_leaders_{tour}_{pool}_{serve|return}_{surface}.csv   leader tables (API)

The history is what Tennis Abstract's ratings never had here: a dated
record. Today's ratings cannot be joined onto past matches without leaking
the future into them; a snapshot per weekly update can, from the week it
was taken.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import unicodedata
from pathlib import Path

import pandas as pd

from tennissharp import config, player_stats as ps
from tennissharp.data import tennisabstract as ta
from tennissharp.data import tennisabstract_leaders as tal
from tennissharp.data import tennismylife as tml

logger = logging.getLogger(__name__)

TOURS = ("atp", "wta")
# Tennis Abstract updates weekly; a stored copy older than this means the
# weekly refresh has stopped reaching it, which is what a run should flag.
TA_MAX_AGE_DAYS = 8
TOUR_OF_SOURCE = {"atp": "atp", "challenger": "atp", "atp_quali": "atp", "wta": "wta"}
PROFILE_SURFACES = ("Hard", "Clay", "Grass")
STAT_KEYS = ("spw", "rpw", "tpw", "dr", "ace_pct", "df_pct", "first_in", "first_won",
             "second_won", "hold_pct", "break_pct", "bp_saved", "bp_converted", "vs_ace_pct")
SURFACE_STAT_KEYS = ("spw", "rpw", "tpw", "dr", "ace_pct", "df_pct", "first_in", "first_won",
                     "second_won", "hold_pct", "break_pct", "bp_saved", "bp_converted")
ELO_COLUMNS = ["elo_rank", "elo", "helo_rank", "helo", "celo_rank", "celo", "gelo_rank", "gelo",
               "peak_elo", "peak_month", "official_rank", "age"]
YELO_COLUMNS = ["yelo_rank", "yelo", "yelo_wins", "yelo_losses"]
HISTORY_COLUMNS = ["ta_updated", "tour", "player", "elo_rank", "elo", "helo", "celo", "gelo",
                   "official_rank", "age", "yelo_rank", "yelo"]
DIGITS = 3


def name_key(name) -> str:
    """Accent-free lower-case tokens: both sources write ASCII names, but a
    hyphen or a stray accent must not split one player into two rows.
    Apostrophes are dropped rather than split on: "O'Connell" and
    "Oconnell" are the same token."""
    folded = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    folded = folded.replace("'", "")
    return " ".join(t for t in re.split(r"[^a-z]+", folded) if t)


# The two sources spell some players differently, and an exact key loses
# them: on the first full run 16 rated ATP players had no statistics for
# that reason alone -- "Bu Yunchaokete" / "Yunchaokete Bu", "Soon Woo Kwon" /
# "Soonwoo Kwon", "Daniel Merida Aguilar" / "Daniel Merida", "Abedallah" /
# "Abdullah Shelbayh". Each rule below pairs only names that are each
# other's single candidate, so two similar players never collapse into one.
def _rule_compact(a: tuple, b: tuple) -> bool:
    return "".join(a) == "".join(b)


def _rule_order(a: tuple, b: tuple) -> bool:
    return sorted(a) == sorted(b)


def _rule_extra_names(a: tuple, b: tuple) -> bool:
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return (len(short) >= 2 and short[0] == long_[0] and set(short) <= set(long_)
            and short[-1] in long_)


def _rule_transliteration(a: tuple, b: tuple) -> bool:
    import difflib
    return (len(a) >= 2 and len(b) >= 2 and a[-1] == b[-1] and a[0][:1] == b[0][:1]
            and difflib.SequenceMatcher(None, a[0], b[0]).ratio() >= 0.75)


_RECONCILE_RULES = (_rule_compact, _rule_order, _rule_extra_names, _rule_transliteration)


def reconcile_keys(stats_keys, ta_keys) -> dict[str, str]:
    """{statistics key -> Tennis Abstract key} for names an exact key misses."""
    left = {k: tuple(k.split()) for k in stats_keys}
    right = {k: tuple(k.split()) for k in ta_keys}
    mapping: dict[str, str] = {}
    for rule in _RECONCILE_RULES:
        cands = {a: [b for b, bt in right.items() if rule(at, bt)] for a, at in left.items()}
        back: dict[str, list[str]] = {}
        for a, bs in cands.items():
            for b in bs:
                back.setdefault(b, []).append(a)
        for a, bs in cands.items():
            if len(bs) == 1 and len(back[bs[0]]) == 1:
                mapping[a] = bs[0]
        for a, b in list(mapping.items()):
            left.pop(a, None)
            right.pop(b, None)
    return mapping


def _r(value):
    return round(value, DIGITS) if isinstance(value, float) else value


def _columns_for_stats() -> list[str]:
    cols = ["tour", "player", "matches", "wins", "losses", "matches_with_stats",
            *STAT_KEYS, "form_last10", "last_match", "ranking_last_seen"]
    for surface in PROFILE_SURFACES:
        pre = surface.lower() + "_"
        cols += [pre + "matches", pre + "wins", pre + "losses"] + [pre + k for k in SURFACE_STAT_KEYS]
    return cols


def player_tours(book: ps.StatBook) -> dict[str, str]:
    """{player -> 'atp' | 'wta'} by where most of the player's matches were."""
    tours = book.long["tour"].map(TOUR_OF_SOURCE).fillna("atp")
    return (book.long.assign(_t=tours).groupby("player")["_t"]
            .agg(lambda s: s.value_counts().idxmax()).to_dict())


def stats_rows(book: ps.StatBook | None) -> pd.DataFrame:
    """One row per player in the statistics window."""
    if book is None or book.long.empty:
        return pd.DataFrame(columns=_columns_for_stats())
    tours = player_tours(book)
    rows = []
    for player in book.players:
        g = book.matches_of(player)
        overall = ps.profile(g)
        if not overall:
            continue
        last10 = g.tail(10)
        ranks = g["rank"].dropna()
        row = {"tour": tours.get(player, "atp"), "player": player,
               "matches": overall["matches"], "wins": overall["wins"], "losses": overall["losses"],
               "matches_with_stats": overall["with_stats"],
               **{k: _r(overall.get(k)) for k in STAT_KEYS},
               "form_last10": f"{int(last10['won'].sum())}-{int(len(last10) - last10['won'].sum())}",
               "last_match": overall["last_date"],
               "ranking_last_seen": int(ranks.iloc[-1]) if len(ranks) else None}
        for surface in PROFILE_SURFACES:
            pre = surface.lower() + "_"
            on = g[g["surface"].astype(str) == surface]
            prof = ps.profile(on) if len(on) else None
            row[pre + "matches"] = prof["matches"] if prof else 0
            row[pre + "wins"] = prof["wins"] if prof else 0
            row[pre + "losses"] = prof["losses"] if prof else 0
            for k in SURFACE_STAT_KEYS:
                row[pre + k] = _r(prof.get(k)) if prof else None
        rows.append(row)
    return pd.DataFrame(rows, columns=_columns_for_stats())


def _ta_part(ta_elo: pd.DataFrame | None, ta_yelo: pd.DataFrame | None) -> pd.DataFrame:
    """Elo and yElo side by side, one row per (tour, player)."""
    elo_cols = ["tour", "player"] + ELO_COLUMNS
    yelo_cols = ["tour", "player"] + YELO_COLUMNS
    elo = (ta_elo.reindex(columns=elo_cols) if ta_elo is not None and len(ta_elo)
           else pd.DataFrame(columns=elo_cols))
    yelo = (ta_yelo.reindex(columns=yelo_cols) if ta_yelo is not None and len(ta_yelo)
            else pd.DataFrame(columns=yelo_cols))
    elo = elo.assign(_key=elo["player"].map(name_key), in_ta_elo=True)
    yelo = yelo.assign(_key=yelo["player"].map(name_key), in_ta_yelo=True)
    elo = elo.drop_duplicates(subset=["tour", "_key"])
    yelo = yelo.drop_duplicates(subset=["tour", "_key"]).rename(columns={"player": "_player_yelo"})
    both = elo.merge(yelo, on=["tour", "_key"], how="outer")
    both["player"] = both["player"].fillna(both["_player_yelo"])
    return both.drop(columns=["_player_yelo"])


def build_profile_table(book: ps.StatBook | None, ta_elo: pd.DataFrame | None,
                        ta_yelo: pd.DataFrame | None) -> pd.DataFrame:
    """The union of rated and recently active players, both tours."""
    stats = stats_rows(book)
    stats = stats.assign(_key=stats["player"].map(name_key), in_stats=True)
    stats = stats.drop_duplicates(subset=["tour", "_key"]).rename(columns={"player": "_player_stats"})
    rated = _ta_part(ta_elo, ta_yelo)
    for tour in TOURS:
        st = set(stats.loc[stats["tour"] == tour, "_key"])
        tk = set(rated.loc[rated["tour"] == tour, "_key"])
        mapping = reconcile_keys(st - tk, tk - st)
        if mapping:
            mask = stats["tour"] == tour
            stats.loc[mask, "_key"] = stats.loc[mask, "_key"].map(lambda k: mapping.get(k, k))
    table = rated.merge(stats, on=["tour", "_key"], how="outer")
    # Tennis Abstract's spelling where it has one; it is the reference the
    # dashboard resolves names against.
    table["player"] = table["player"].fillna(table["_player_stats"])
    for flag in ("in_ta_elo", "in_ta_yelo", "in_stats"):
        table[flag] = table[flag].astype("boolean").fillna(False).astype(bool)
    for col in ("matches", "wins", "losses", "matches_with_stats",
                *(s.lower() + "_" + k for s in PROFILE_SURFACES for k in ("matches", "wins", "losses"))):
        table[col] = pd.to_numeric(table[col], errors="coerce").fillna(0).astype(int)
    order = ["tour", "player", "official_rank", "age", *ELO_COLUMNS[:2], *ELO_COLUMNS[2:10],
             "peak_elo", "peak_month", *YELO_COLUMNS]
    order = list(dict.fromkeys(order))
    rest = [c for c in _columns_for_stats() if c not in ("tour", "player")]
    order += rest + ["in_ta_elo", "in_ta_yelo", "in_stats"]
    table = table.reindex(columns=order)
    table = table.sort_values(["tour", "elo_rank", "matches"], ascending=[True, True, False],
                              na_position="last", kind="stable")
    return table.reset_index(drop=True)


def append_elo_history(path: Path, ta_elo: pd.DataFrame | None, ta_yelo: pd.DataFrame | None,
                       today: dt.date | None = None) -> int:
    """Add one dated snapshot per tour, keyed by Tennis Abstract's own update
    date, unless that update is already in the file. Returns rows added."""
    if ta_elo is None or ta_elo.empty:
        return 0
    snap = _ta_part(ta_elo, ta_yelo)
    dates = ta_elo.groupby("tour")["ta_updated"].first().to_dict() if "ta_updated" in ta_elo else {}
    fallback = (today or dt.date.today()).isoformat()
    snap["ta_updated"] = snap["tour"].map(
        lambda t: dates[t] if isinstance(dates.get(t), str) and dates[t] else fallback)
    snap = snap.reindex(columns=HISTORY_COLUMNS)
    path = Path(path)
    if path.exists() and path.stat().st_size:
        seen = pd.read_csv(path, usecols=["ta_updated", "tour"]).drop_duplicates()
        have = set(zip(seen["ta_updated"].astype(str), seen["tour"].astype(str)))
        snap = snap[[(str(d), str(t)) not in have for d, t in zip(snap["ta_updated"], snap["tour"])]]
    if snap.empty:
        return 0
    header = not path.exists() or path.stat().st_size == 0
    snap.to_csv(path, mode="a", header=header, index=False)
    return int(len(snap))


def write_leader_tables(book: ps.StatBook, out_dir: Path) -> int:
    """The 50 leader CSVs behind the /leaders API endpoint, same names as
    when they were read from tennisabstract.com/jsmatches/."""
    n = 0
    for tour, pools in tal.POOLS_BY_TOUR.items():
        for pool in pools:
            tables = ps.leader_tables(book, tour, pool)
            slug = pool.replace("-", "")
            for surface in tal.SURFACES:
                key = surface.lower()
                tables[key].to_csv(out_dir / f"ta_leaders_{tour}_{slug}_serve_{key}.csv", index=False)
                tables["return_" + key].to_csv(out_dir / f"ta_leaders_{tour}_{slug}_return_{key}.csv",
                                               index=False)
                n += 2
    return n


def _read(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path)
    except (OSError, ValueError):
        return None


def summarize(table: pd.DataFrame, book, ta_elo, ta_yelo, today: dt.date, errors: list[str]) -> dict:
    def dates(df):
        if df is None or df.empty or "ta_updated" not in df:
            return {}
        return {t: (None if pd.isna(d) else str(d)) for t, d in df.groupby("tour")["ta_updated"].first().items()}

    last = {}
    if book is not None and not book.long.empty:
        tours = book.long["tour"].map(TOUR_OF_SOURCE)
        last = {t: book.long.loc[tours == t, "date"].max().date().isoformat()
                for t in TOURS if (tours == t).any()}
    players = {}
    for tour in TOURS:
        t = table[table["tour"] == tour]
        players[tour] = {"total": int(len(t)), "with_elo": int(t["in_ta_elo"].sum()),
                         "with_yelo": int(t["in_ta_yelo"].sum()), "with_stats": int(t["in_stats"].sum()),
                         "with_elo_and_stats": int((t["in_ta_elo"] & t["in_stats"]).sum())}
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "ta_elo_last_update": dates(ta_elo),
        "ta_yelo_last_update": dates(ta_yelo),
        "stats_window": {"from": (today - dt.timedelta(days=ps.WINDOW_DAYS)).isoformat(),
                         "to": today.isoformat()},
        "stats_last_match": last,
        "players": players,
        "errors": errors,
    }


def _previous_meta(out_dir: Path) -> dict:
    try:
        return json.loads((out_dir / "player_profiles_meta.json").read_text())
    except (OSError, ValueError):
        return {}


def ta_age_days(meta: dict, now: dt.datetime | None = None) -> float | None:
    """Days since Tennis Abstract's Elo was last read successfully."""
    stamp = (meta.get("ta_fetched_at") or {}).get("elo")
    if not stamp:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    return (now - dt.datetime.fromisoformat(stamp)).total_seconds() / 86400.0


def refresh_surface_speed(out_dir: Path) -> int:
    """Tennis Abstract's per-edition surface speed, the trained feature and
    the court-surface lookup. Kept with the other Tennis Abstract reads
    because the same hosts refuse the same networks."""
    hist = ta.fetch_surface_speed_history(config.START_SEASON)
    if hist.empty:
        raise RuntimeError("no surface-speed ratings returned")
    hist.to_csv(out_dir / "ta_surface_speed_history.csv", index=False)
    return int(len(hist))


def refresh(out_dir: Path | None = None, today: dt.date | None = None,
            surface_speed: bool = False) -> dict:
    """Fetch, compute and write everything listed in the module docstring.

    Each source is best effort. A failed Tennis Abstract fetch falls back to
    the last saved ratings so the table still builds; a failed statistics
    load leaves the previous tables in place. Every failure is listed in
    the returned summary's `errors` (and in the meta file)."""
    out_dir = Path(out_dir or config.PROCESSED_DIR)
    today = today or dt.date.today()
    errors: list[str] = []
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    fetched = dict(_previous_meta(out_dir).get("ta_fetched_at") or {})

    elo_fresh = False
    try:
        ta_elo = ta.fetch_all_elo_ratings()
        elo_fresh = True
        fetched["elo"] = stamp
        ta_elo.to_csv(out_dir / "ta_elo_current.csv", index=False)
        for tour in TOURS:
            ta.filter_by_tour(ta_elo, tour).to_csv(out_dir / f"ta_elo_{tour}_general.csv", index=False)
        logger.info("Tennis Abstract Elo: %d players (update %s)", len(ta_elo),
                    ta_elo["ta_updated"].dropna().unique().tolist())
    except Exception as exc:  # network, layout change
        logger.exception("Tennis Abstract Elo not refreshed")
        errors.append(f"Tennis Abstract Elo nicht aktualisiert: {exc}")
        ta_elo = _read(out_dir / "ta_elo_current.csv")

    try:
        ta_yelo = ta.fetch_all_yelo_ratings()
        fetched["yelo"] = stamp
        ta_yelo.to_csv(out_dir / "ta_yelo_current.csv", index=False)
        logger.info("Tennis Abstract yElo: %d players", len(ta_yelo))
    except Exception as exc:
        logger.exception("Tennis Abstract yElo not refreshed")
        errors.append(f"Tennis Abstract yElo nicht aktualisiert: {exc}")
        ta_yelo = _read(out_dir / "ta_yelo_current.csv")

    # Only a fresh fetch is a snapshot. The fallback copy is last week's, and
    # filing it under today's date would date old ratings as new ones.
    if elo_fresh:
        try:
            added = append_elo_history(out_dir / "ta_elo_history.csv", ta_elo, ta_yelo, today)
            logger.info("Elo history: %d rows added", added)
        except Exception as exc:
            logger.exception("Elo history not written")
            errors.append(f"Elo-Historie nicht geschrieben: {exc}")

    if surface_speed:
        try:
            n = refresh_surface_speed(out_dir)
            fetched["surface_speed"] = stamp
            logger.info("Tennis Abstract surface speed: %d tournament editions", n)
        except Exception as exc:
            logger.exception("Surface speed not refreshed")
            errors.append(f"Belagstempo nicht aktualisiert: {exc}")

    book = None
    try:
        matches = tml.load_all(start_season=today.year - 1)
        if matches.empty:
            raise RuntimeError("no TennisMyLife matches")
        book = ps.StatBook(matches, as_of=today)
        logger.info("Statistics window: %d players, %d match rows", len(book.players), len(book.long))
    except Exception as exc:
        logger.exception("Statistics not refreshed")
        errors.append(f"Statistiken nicht aktualisiert: {exc}")

    table = build_profile_table(book, ta_elo, ta_yelo)
    if book is not None or not table.empty:
        for tour in TOURS:
            table[table["tour"] == tour].to_csv(out_dir / f"player_profiles_{tour}.csv", index=False)
    if book is not None:
        try:
            write_leader_tables(book, out_dir)
        except Exception as exc:
            logger.exception("Leader tables not written")
            errors.append(f"Bestenlisten nicht geschrieben: {exc}")

    meta = summarize(table, book, ta_elo, ta_yelo, today, errors)
    meta["ta_fetched_at"] = fetched
    meta["statistics_ok"] = book is not None
    (out_dir / "player_profiles_meta.json").write_text(json.dumps(meta, indent=1))
    return meta
