#!/usr/bin/env python3
"""Full briefing for one matchup, assembled from every source in the repo.

    python scripts/analyze_match.py "Sinner" "Alcaraz" --surface Hard

Pulls together our own surface-Elo, Tennis Abstract's Elo, the Serve/Return
leaderboards, tournament surface speed, head-to-head, and -- when the match
is in the cached TennisExplorer schedule -- the current market price plus
the model's own probability and whether that clears the value threshold.

Sources name players differently (`Sinner J.` in our match history vs
`Jannik Sinner` on Tennis Abstract), so every lookup goes through
`resolve_name`, which matches on (lastname, first initial) rather than
requiring one canonical spelling.

The model's probability is only shown when a market price is available: it
is trained with the de-vigged market price as a feature (see model.py), so
scoring it without one would silently feed a fabricated input. Without odds
the briefing falls back to the Elo-only probability and says so.
"""
import _bootstrap  # noqa: F401
import argparse
import unicodedata

import joblib
import pandas as pd

from tennissharp import config, odds_math
from tennissharp.backtest import DEFAULT_EDGE_THRESHOLD

SURFACES = ("Hard", "Clay", "Grass", "Carpet")


def _fold(text: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", str(text))
                       if not unicodedata.combining(c))
    return stripped.strip().lower()


def name_key(name: str) -> tuple[str, str]:
    """(lastname, first initial) -- the one thing every source agrees on.

    Handles both `Sinner J.` (our match history, TennisExplorer) and
    `Jannik Sinner` (Tennis Abstract). Multi-word surnames stay attached in
    the "Lastname F." form because the initial is always the final token,
    so everything before it is the surname.
    """
    parts = _fold(name).replace(",", " ").split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")                                   # bare "Sinner"
    if len(parts[-1].rstrip(".")) == 1:
        return (" ".join(parts[:-1]), parts[-1].rstrip("."))    # "Sinner J."
    return (" ".join(parts[1:]), parts[0][:1])                  # "Jannik Sinner"


def resolve_name(query: str, candidates) -> str | None:
    """Best match for `query` among `candidates`. Exact (lastname, initial)
    wins; a unique surname-only hit is accepted as a fallback so a bare
    "Alcaraz" resolves, but an ambiguous one returns None rather than
    silently picking the wrong player.
    """
    q_last, q_init = name_key(query)
    if not q_last:
        return None
    keyed = [(name_key(c), c) for c in candidates]
    exact = [c for (last, init), c in keyed if last == q_last and init == q_init]
    if exact:
        return exact[0]
    surname_only = {c for (last, _), c in keyed if last == q_last}
    if len(surname_only) == 1:
        return surname_only.pop()
    # Bare query like "Alcaraz" against "Alcaraz C." -- query carried no initial.
    if not q_init:
        loose = {c for (last, _), c in keyed if last == q_last}
        if len(loose) == 1:
            return loose.pop()
    return None


def _load_csv(name: str) -> pd.DataFrame | None:
    path = config.PROCESSED_DIR / name
    return pd.read_csv(path) if path.exists() else None


def _fmt(value, spec=".1f", dash="--"):
    return dash if value is None or pd.isna(value) else format(value, spec)


def _pct(value):
    return "--" if value is None or pd.isna(value) else f"{value * 100:.1f}%"


def _leaders_row(tour: str, stat: str, surface: str, player_query: str):
    """Search the Serve/Return leaderboards across all player pools."""
    for pool in ("top50", "51100", "challenger"):
        df = _load_csv(f"ta_leaders_{tour}_{pool}_{stat}_{surface.lower()}.csv")
        if df is None or df.empty:
            continue
        hit = resolve_name(player_query, df["player"].tolist())
        if hit:
            return df[df["player"] == hit].iloc[0], pool
    return None, None


def analyze(query_a: str, query_b: str, surface: str, best_of: int) -> None:
    state = joblib.load(config.MODELS_DIR / "live_state.joblib")
    snapshot = state.elo.snapshot()
    roster = snapshot["player"].tolist()

    a = resolve_name(query_a, roster)
    b = resolve_name(query_b, roster)
    for query, hit in ((query_a, a), (query_b, b)):
        if not hit:
            raise SystemExit(f"Kein Spieler gefunden fuer '{query}'. "
                             "Bitte Nachnamen genauer angeben (z.B. \"Sinner J.\").")

    ta_elo = _load_csv("ta_elo_current.csv")
    tour = "atp"
    if ta_elo is not None:
        hit = resolve_name(a, ta_elo["player"].tolist())
        if hit:
            tour = ta_elo[ta_elo["player"] == hit].iloc[0]["tour"]

    print(f"\n{'=' * 72}\n  {a}  vs  {b}   [{surface}, best of {best_of}, {tour.upper()}]\n{'=' * 72}")

    # -- our own surface Elo -------------------------------------------------
    ra = snapshot[snapshot["player"] == a].iloc[0]
    rb = snapshot[snapshot["player"] == b].iloc[0]
    skey = surface.lower()
    print(f"\nEIGENES ELO (aus {int(ra['matches_played'])}/{int(rb['matches_played'])} Matches)")
    print(f"  {'':22} {a:>18} {b:>18}")
    print(f"  {'Elo gesamt':22} {ra['elo_overall']:>18.1f} {rb['elo_overall']:>18.1f}")
    if f"elo_{skey}" in snapshot.columns:
        na, nb = int(ra[f"matches_{skey}"]), int(rb[f"matches_{skey}"])
        print(f"  {'Elo ' + surface:22} {ra['elo_' + skey]:>18.1f} {rb['elo_' + skey]:>18.1f}")
        print(f"  {'  davon Matches':22} {na:>18} {nb:>18}")
        if min(na, nb) < 10:
            print("  ! Wenig Belag-Matches -- Belags-Elo hier nur schwach belegt.")

    # -- Tennis Abstract Elo -------------------------------------------------
    if ta_elo is not None:
        ha, hb = resolve_name(a, ta_elo["player"].tolist()), resolve_name(b, ta_elo["player"].tolist())
        if ha and hb:
            ta_a = ta_elo[ta_elo["player"] == ha].iloc[0]
            ta_b = ta_elo[ta_elo["player"] == hb].iloc[0]
            print(f"\nTENNIS ABSTRACT ELO   ({ha} / {hb})")
            print(f"  {'':22} {ha:>18} {hb:>18}")
            for label, col in (("Elo (Rang)", "elo"), ("hElo Hard", "helo"),
                                ("cElo Clay", "celo"), ("gElo Grass", "gelo"),
                                ("Peak Elo", "peak_elo")):
                if col not in ta_elo.columns:
                    continue
                sa, sb = _fmt(ta_a[col]), _fmt(ta_b[col])
                if col == "elo":
                    sa += f" (#{_fmt(ta_a.get('elo_rank'), '.0f')})"
                    sb += f" (#{_fmt(ta_b.get('elo_rank'), '.0f')})"
                print(f"  {label:22} {sa:>18} {sb:>18}")

    # -- Serve / Return ------------------------------------------------------
    for stat, cols in (
        ("serve", [("SPW", "spw"), ("Aces%", "ace_pct"), ("DF%", "df_pct"),
                    ("1. Aufschlag rein", "first_in_pct"), ("1. gewonnen", "first_win_pct"),
                    ("2. gewonnen", "second_win_pct"), ("Hold%", "hold_pct")]),
        ("return", [("RPW", "rpw"), ("Break%", "break_pct"), ("vs Ace%", "vs_ace_pct"),
                     ("vs 1. gewonnen", "vs_first_win_pct"),
                     ("vs 2. gewonnen", "vs_second_win_pct")]),
    ):
        row_a, pool_a = _leaders_row(tour, stat, surface, a)
        row_b, pool_b = _leaders_row(tour, stat, surface, b)
        if row_a is None and row_b is None:
            continue
        label = "SERVE" if stat == "serve" else "RETURN"
        print(f"\n{label} ({surface}, letzte 52 Wochen)")
        na = f"{row_a['matches']:.0f} M [{pool_a}]" if row_a is not None else "keine Daten"
        nb = f"{row_b['matches']:.0f} M [{pool_b}]" if row_b is not None else "keine Daten"
        print(f"  {'':22} {na:>18} {nb:>18}")
        for label_, col in cols:
            va = _pct(row_a[col]) if row_a is not None and col in row_a else "--"
            vb = _pct(row_b[col]) if row_b is not None and col in row_b else "--"
            print(f"  {label_:22} {va:>18} {vb:>18}")
        for row, name in ((row_a, a), (row_b, b)):
            if row is not None and row["matches"] < 10:
                print(f"  ! {name}: nur {row['matches']:.0f} Matches auf {surface} "
                      "-- Stichprobe zu klein fuer belastbare Aussagen.")

    # -- head to head --------------------------------------------------------
    wa, wb = state.h2h_wins(a, b)
    print(f"\nHEAD-TO-HEAD (aus unserer Match-Historie)\n  {a} {wa} : {wb} {b}"
          + ("   (noch nie gegeneinander)" if wa + wb == 0 else ""))

    # -- form / workload -----------------------------------------------------
    now = pd.Timestamp.now().normalize()
    print("\nFORM & BELASTUNG")
    print(f"  {'':22} {a:>18} {b:>18}")
    print(f"  {'Form (letzte Siege)':22} {_pct(state.form_rate(a)):>18} {_pct(state.form_rate(b)):>18}")
    print(f"  {'Tage Pause':22} {state.days_rest(a, now):>18.0f} {state.days_rest(b, now):>18.0f}")
    print(f"  {'Matches (30 Tage)':22} {state.matches_recent(a, now):>18} {state.matches_recent(b, now):>18}")

    # -- market + model ------------------------------------------------------
    sched = _load_csv("tennisexplorer_upcoming.csv")
    odds_a = odds_b = None
    if sched is not None and not sched.empty:
        for _, m in sched.iterrows():
            p1 = resolve_name(str(m["player1"]), [a, b])
            p2 = resolve_name(str(m["player2"]), [a, b])
            if p1 and p2 and p1 != p2:
                odds_a, odds_b = (m["odds1"], m["odds2"]) if p1 == a else (m["odds2"], m["odds1"])
                print(f"\nMARKT (TennisExplorer: {m['player1']} vs {m['player2']}, {m['tournament']})")
                break

    speed_row = None
    speed_df = _load_csv("ta_surface_speed_history.csv")
    if speed_df is not None and not speed_df.empty:
        latest = speed_df[speed_df["surface"].str.lower() == skey]
        if not latest.empty:
            speed_row = latest.sort_values("date").iloc[-1]

    surface_speed = float(speed_row["surface_speed"]) if speed_row is not None else 1.0
    from tennissharp.value_finder import _features_for_matchup, elo_only_probability

    elo_p = elo_only_probability(state, a, b, surface)
    print("\nPROGNOSE")
    print(f"  Nur Elo:            {a} {elo_p:.1%}  |  {b} {1 - elo_p:.1%}")

    if pd.notna(odds_a) and pd.notna(odds_b) and odds_a and odds_b:
        # Must match features.attach_market_probability exactly (Shin, not
        # multiplicative, and the same clipped logit) -- the model was trained
        # on that transform, so any other de-vig feeds it an input it has
        # never seen and quietly shifts every probability it returns.
        import numpy as np
        fair_a, fair_b = odds_math.shin_devig([float(odds_a), float(odds_b)])
        model = joblib.load(config.MODELS_DIR / "win_probability_model.joblib")
        feats = _features_for_matchup(state, a, b, surface, best_of, surface_speed)
        clipped = float(np.clip(fair_a, 1e-6, 1 - 1e-6))
        feats["market_logit"] = float(np.log(clipped / (1 - clipped)))
        from tennissharp.model import feature_columns
        X = pd.DataFrame([feats])[feature_columns(True)]
        model_p = float(model.predict_proba(X)[0][1])

        print(f"  Modell (mit Markt): {a} {model_p:.1%}  |  {b} {1 - model_p:.1%}")
        print(f"  Quote:              {a} {odds_a}  |  {b} {odds_b}")
        print(f"  Markt fair:         {a} {fair_a:.1%}  |  {b} {fair_b:.1%}")

        print("\nWERT-BEWERTUNG")
        any_bet = False
        for name, mp, fp, price in ((a, model_p, fair_a, odds_a), (b, 1 - model_p, fair_b, odds_b)):
            edge = odds_math.edge(mp, fp)
            mark = "WETTE" if edge > DEFAULT_EDGE_THRESHOLD else "     "
            any_bet |= edge > DEFAULT_EDGE_THRESHOLD
            print(f"  {mark} {name:20} Edge {edge:+6.1%}   (Schwelle {DEFAULT_EDGE_THRESHOLD:.0%})")
        if not any_bet:
            print("  -> Keine Seite erreicht die Schwelle. Kein Signal.")
    else:
        print("  Modell (mit Markt): -- keine Quote im Zeitplan-Cache gefunden.")
        print("     Das Modell ist mit dem Marktpreis als Merkmal trainiert; ohne Quote")
        print("     waere die Ausgabe erfunden. Oben steht deshalb nur der Elo-Wert.")

    print("\n" + "-" * 72)
    print("Erinnerung: scripts/audit_edge.py findet keine Information ueber den Markt")
    print("hinaus (information gain -0.00078). Diese Analyse ist Recherche, kein")
    print("belegter Vorteil -- siehe README, Abschnitt 'Can this actually beat...'.")
    print("-" * 72 + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("player_a")
    p.add_argument("player_b")
    p.add_argument("--surface", default="Hard", choices=SURFACES)
    p.add_argument("--best-of", type=int, default=3, choices=(3, 5))
    args = p.parse_args()
    analyze(args.player_a, args.player_b, args.surface, args.best_of)


if __name__ == "__main__":
    main()
