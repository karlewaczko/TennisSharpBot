"""Pure text formatters: DataFrame/dict in, Telegram-HTML string out.

Kept free of any Telegram or network imports so it's trivially unit-testable.
Uses Telegram's HTML parse mode (only needs to escape &, <, > -- MarkdownV2's
escaping rules are far more error-prone for text with punctuation like
player names "O'Connell" or scores "6-4").
"""
from __future__ import annotations

from html import escape

import pandas as pd

DISCLAIMER = (
    "⚠️ Keine Anlage-/Wettberatung. Nur Recherche-Signal, keine Garantie. "
    "LUGAS-Limit (1.000 €/Monat) beachten, nur GGL-lizenzierte Anbieter nutzen."
)


def format_rankings(df: pd.DataFrame, tour: str, source: str) -> str:
    if df.empty:
        return f"Keine Elo-Daten für {tour.upper()} gefunden."
    label = "Tennis Abstract" if source == "ta" else "eigene, ATP+WTA gemischt"
    title = tour.upper() if source == "ta" else "Top"
    lines = [f"<b>{escape(title)} Elo-Rangliste ({label})</b>"]
    for i, row in enumerate(df.itertuples(index=False), start=1):
        elo = row.elo if hasattr(row, "elo") else row.elo_overall
        lines.append(f"{i}. {escape(str(row.player))} — {elo:.0f}")
    if source != "ta":
        lines.append("\n(eigene Elo trennt Touren aktuell nicht -- für reine ATP/WTA-Liste Quelle 'ta' nutzen)")
    return "\n".join(lines)


def format_surface_speed(df: pd.DataFrame, tournament: str | None) -> str:
    if df.empty:
        target = f"'{tournament}'" if tournament else "der aktuellen Saison"
        return f"Keine Surface-Speed-Daten für {escape(target)} gefunden."
    title = f"Surface Speed: {escape(tournament)}" if tournament else "Schnellste Turniere (aktuelle Saison)"
    lines = [f"<b>{title}</b>"]
    for row in df.itertuples(index=False):
        date_str = row.date.date() if hasattr(row.date, "date") else row.date
        lines.append(
            f"{escape(str(row.tournament))} ({date_str}, {escape(str(row.surface))}): "
            f"Speed {row.surface_speed:.2f}, Ace% {row.ace_pct * 100:.1f}%"
        )
    return "\n".join(lines)


def format_upcoming(df: pd.DataFrame, tour: str | None) -> str:
    if df.empty:
        target = tour.upper() if tour else "alle Touren"
        return f"Keine anstehenden Spiele für {escape(target)} gefunden."
    lines = [f"<b>Anstehende Spiele{' (' + tour.upper() + ')' if tour else ''}</b>"]
    for row in df.itertuples(index=False):
        odds = f" | Quote {row.odds1:.2f} / {row.odds2:.2f}" if pd.notna(row.odds1) else ""
        lines.append(f"{escape(str(row.tournament))}: {escape(str(row.player1))} vs "
                      f"{escape(str(row.player2))}{odds}")
    return "\n".join(lines)


def format_h2h(result: dict) -> str:
    p1, p2 = result["player1"], result["player2"]
    w1, w2 = result["wins1"], result["wins2"]
    lines = [f"<b>Head-to-Head: {escape(p1)} vs {escape(p2)}</b>", f"{w1} : {w2}"]
    history = result.get("history")
    if history is not None and not history.empty:
        lines.append("")
        lines.append("Letzte Begegnungen:")
        for _, group in history.groupby(history.index // 2):
            if len(group) != 2:
                continue
            winner = group.loc[group["sets_won"].idxmax()]
            loser = group.loc[group["sets_won"].idxmin()]
            round_str = winner.get("round")
            round_part = f" ({escape(str(round_str))})" if pd.notna(round_str) else ""
            lines.append(f"{winner['year']} {escape(str(winner['tournament']))}{round_part}: "
                          f"{escape(str(winner['player']))} d. {escape(str(loser['player']))}")
    return "\n".join(lines)


def format_value_bets(df: pd.DataFrame) -> str:
    if df.empty:
        return "Keine Value Bets über der Edge-Schwelle gefunden."
    lines = ["<b>Value Bets</b>"]
    for row in df.itertuples(index=False):
        lines.append(
            f"{escape(str(row.player))} vs {escape(str(row.opponent))} @ {escape(str(row.bookmaker))}\n"
            f"  Quote {row.odds:.2f} | Modell {row.model_prob * 100:.1f}% | "
            f"Markt {row.market_fair_prob * 100:.1f}% | Edge {row.edge * 100:.1f}% | "
            f"Stake-Vorschlag {row.suggested_stake:.2f}"
        )
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_error(message: str) -> str:
    return f"❌ {escape(message)}"
