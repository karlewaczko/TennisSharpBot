"""Name resolution for scripts/analyze_match.py.

The briefing joins five sources that spell players differently, so this
matcher is the single point where a silent mismatch would show one player's
Elo next to another player's serve stats. Every case below is a spelling
that actually occurs in the project's data.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location("analyze_match", _SCRIPTS / "analyze_match.py")


@pytest.fixture(scope="module")
def am():
    """Import the script without executing main() -- it lives in scripts/,
    not the installed package, so it needs loading by path, and scripts/ must
    be importable for its `import _bootstrap` line to resolve.
    """
    sys.path.insert(0, str(_SCRIPTS))
    try:
        mod = importlib.util.module_from_spec(_SPEC)
        _SPEC.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(_SCRIPTS))


# Spellings taken verbatim from the Elo roster built off tennis-data.co.uk.
ROSTER = ["Sinner J.", "Alcaraz C.", "Djokovic N.", "Novak D.",
          "Auger-Aliassime F.", "Zverev A.", "Zverev M.",
          "Pliskova Ka.", "Pliskova Kr.", "Cerundolo J.M.", "Struff J.L.",
          "Li A.", "Raducanu E.", "Raducànu E."]
TA_NAMES = ["Jannik Sinner", "Carlos Alcaraz", "Felix Auger Aliassime", "Elena Rybakina"]


def test_explicit_initial_gives_one_reading(am):
    assert am.name_readings("Sinner J.") == [("sinner", "j")]
    assert am.name_readings("J. Sinner") == [("sinner", "j")]
    assert am.name_readings("Sinner") == [("sinner", "")]


def test_bare_full_name_is_ordered_likeliest_first(am):
    """Readings are tried in order, not pooled -- see name_readings' docstring
    for the Djokovic/Novak collision that ordering exists to prevent."""
    readings = am.name_readings("Novak Djokovic")
    assert readings[0] == ("djokovic", "novak")
    assert ("novak", "djokovic") in readings          # available, but last resort


def test_accents_and_hyphens_are_normalised(am):
    assert am.name_readings("Möller H.") == [("moller", "h")]
    # `Auger-Aliassime F.` and `Felix Auger Aliassime` must reach each other.
    assert am.resolve_name("Felix Auger Aliassime", ROSTER) == "Auger-Aliassime F."
    assert am.resolve_name("Auger-Aliassime F.", TA_NAMES) == "Felix Auger Aliassime"


def test_first_name_collision_does_not_block_the_surname_match(am):
    """`Novak Djokovic` once resolved to nobody because Dennis Novak is also
    a real player and both readings were weighted equally -- dropping the
    world number one out of every lookup."""
    assert am.resolve_name("Novak Djokovic", ROSTER) == "Djokovic N."
    assert am.resolve_name("Dennis Novak", ROSTER) == "Novak D."


def test_multi_letter_initials_separate_the_pliskova_sisters(am):
    assert am.resolve_name("Karolina Pliskova", ROSTER) == "Pliskova Ka."
    assert am.resolve_name("Kristyna Pliskova", ROSTER) == "Pliskova Kr."
    # The bare surname stays ambiguous -- two different players.
    assert am.resolve_name("Pliskova", ROSTER) is None


def test_compound_given_names_reach_dotted_initials(am):
    assert am.resolve_name("Juan Manuel Cerundolo", ROSTER) == "Cerundolo J.M."
    assert am.resolve_name("Jan Lennard Struff", ROSTER) == "Struff J.L."


def test_two_letter_surnames_are_not_mistaken_for_initials(am):
    """Only a trailing dot marks an abbreviation. A length test looked
    reasonable and silently lost every `Li`, `Wu` and `Ng`."""
    assert am.resolve_name("Ann Li", ROSTER) == "Li A."
    assert am.name_readings("Ann Li")[0] == ("li", "ann")


def test_duplicate_spellings_of_one_player_resolve(am):
    """`Raducanu E.` and `Raducànu E.` are the same person entered twice;
    folding to one key is not an ambiguity."""
    assert am.resolve_name("Emma Raducanu", ROSTER) in {"Raducanu E.", "Raducànu E."}


def test_genuinely_different_players_stay_unresolved(am):
    """Two Zverevs: picking one silently would put the wrong player's stats
    in the briefing."""
    assert am.resolve_name("Zverev", ROSTER) is None
    assert am.resolve_name("Zverev A.", ROSTER) == "Zverev A."
    assert am.resolve_name("Mischa Zverev", ROSTER) == "Zverev M."


def test_resolves_across_naming_conventions(am):
    assert am.resolve_name("Sinner J.", TA_NAMES) == "Jannik Sinner"
    assert am.resolve_name("Jannik Sinner", ROSTER) == "Sinner J."
    assert am.resolve_name("Sinner", ROSTER) == "Sinner J."


def test_surname_first_odds_table_spelling(am):
    """TennisExplorer's schedule writes `Paul T.` while the odds table on the
    same page writes `Paul Tommy`."""
    assert am.resolve_name("Paul Tommy", ["Paul T.", "Cobolli F."]) == "Paul T."
    assert am.resolve_name("Cobolli Flavio", ["Paul T.", "Cobolli F."]) == "Cobolli F."


def test_unknown_player_returns_none(am):
    assert am.resolve_name("Federer", ROSTER) is None
    assert am.resolve_name("", ROSTER) is None


def test_internal_dot_counts_as_an_abbreviation(am):
    """The roster spells one player `P.H.` in one row and `P.H` (no closing
    dot) in another; both are initials, not a surname."""
    assert am.name_readings("Herbert P.H") == [("herbert", "ph")]
    assert am.name_readings("Herbert P.H.") == [("herbert", "ph")]


def test_weight_breaks_ties_toward_the_fullest_history(am):
    """Pierre-Hugues Herbert occupies four roster rows with his history split
    across them. Without a weight the longest spelling wins, which is the
    16-match row; callers pass matches_played so the 210-match row wins."""
    rows = ["Herbert P.", "Herbert P.H", "Herbert P.H.", "Herbert P-H."]
    played = {"Herbert P.": 14, "Herbert P.H": 16, "Herbert P.H.": 210, "Herbert P-H.": 1}
    assert am.resolve_name("Herbert P.", rows, weight=played.get) == "Herbert P.H."
    # Still deterministic without one.
    assert am.resolve_name("Herbert P.", rows) in rows


def test_weight_never_merges_two_different_players(am):
    """A weight must not turn a genuine ambiguity into a confident answer."""
    rows = ["Zverev A.", "Zverev M."]
    assert am.resolve_name("Zverev", rows, weight={"Zverev A.": 500}.get) is None


def test_candidate_readings_are_ranked_too(am):
    """`Maria T.` means surname Maria. Tatjana Maria matches on her primary
    reading; Maria Timofeeva matches only via the last-resort surname-first
    reading, where her *first* name is read as a surname. Pooling the two made
    the query ambiguous and dropped both players."""
    rows = ["Tatjana Maria", "Maria Timofeeva", "Maria Sakkari"]
    assert am.resolve_name("Maria T.", rows) == "Tatjana Maria"
    # The other two stay reachable by their own primary reading.
    assert am.resolve_name("Timofeeva M.", rows) == "Maria Timofeeva"
    assert am.resolve_name("Sakkari M.", rows) == "Maria Sakkari"
