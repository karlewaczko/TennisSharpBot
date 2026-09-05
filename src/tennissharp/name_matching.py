"""Best-effort matching between full player names (live odds feeds use
'Novak Djokovic') and the 'Lastname F.' style used throughout tennis-data.co.uk
history (our Elo/form/H2H keys).

This is inherently fuzzy for compound surnames ("Del Potro", "van de Zandschulp")
and is only used by the *optional* live value-bet finder -- the historical
backtest never needs it, since results and odds already share one naming
scheme there.
"""
from __future__ import annotations

import re
import unicodedata

_INITIAL_RE = re.compile(r"^[A-Z]\.(?:[A-Z]\.)?$")


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def parse_td_style_name(name: str) -> tuple[str, str]:
    """'Djokovic N.' -> ('djokovic', 'n'); 'Del Potro J.M.' -> ('del potro', 'jm')."""
    tokens = name.strip().split(" ")
    idx = len(tokens)
    while idx > 0 and _INITIAL_RE.match(tokens[idx - 1]):
        idx -= 1
    lastname = " ".join(tokens[:idx]) if idx > 0 else name
    initials = "".join(tokens[idx:]).replace(".", "")
    return _strip_accents(lastname).lower(), _strip_accents(initials).lower()


def build_name_index(known_players: list[str]) -> dict[str, list[str]]:
    """Map normalized lastname -> list of original 'Lastname F.' keys sharing it."""
    index: dict[str, list[str]] = {}
    for player in known_players:
        lastname, _ = parse_td_style_name(player)
        index.setdefault(lastname, []).append(player)
    return index


def match_full_name(full_name: str, known_players: list[str],
                     name_index: dict[str, list[str]] | None = None) -> str | None:
    """Best-effort match of a 'Firstname Lastname' string to a known
    'Lastname F.' key. Returns None if no confident match is found.
    """
    index = name_index or build_name_index(known_players)
    tokens = _strip_accents(full_name.strip()).lower().split(" ")
    if not tokens:
        return None
    first_initial = tokens[0][0] if tokens[0] else ""

    # Try progressively shorter suffixes as the "lastname" (handles most
    # 1-2 word surnames without needing a name-particle dictionary).
    for start in range(1, len(tokens)):
        candidate_lastname = " ".join(tokens[start:])
        candidates = index.get(candidate_lastname)
        if not candidates:
            continue
        if len(candidates) == 1:
            return candidates[0]
        for player in candidates:
            _, initials = parse_td_style_name(player)
            if initials.startswith(first_initial):
                return player
        return candidates[0]
    return None
