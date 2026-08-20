"""Name resolution for scripts/analyze_match.py.

The briefing joins five sources that spell players differently
(`Sinner J.` in our match history, `Jannik Sinner` on Tennis Abstract), so
this matcher is the single point where a silent mismatch would show one
player's Elo next to another player's serve stats.
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


ROSTER = ["Sinner J.", "Alcaraz C.", "Djokovic N.", "Auger Aliassime F.",
          "Ugo Carabelli C.", "Zverev A.", "Zverev M."]
TA_NAMES = ["Jannik Sinner", "Carlos Alcaraz", "Felix Auger Aliassime", "Elena Rybakina"]


def test_name_keys_unambiguous_when_an_initial_is_present(am):
    assert am.name_keys("Sinner J.") == {("sinner", "j")}
    assert am.name_keys("J. Sinner") == {("sinner", "j")}
    assert am.name_keys("Sinner") == {("sinner", "")}
    # Multi-word surnames stay intact.
    assert am.name_keys("Auger Aliassime F.") == {("auger aliassime", "f")}


def test_name_keys_offers_both_orders_for_a_bare_full_name(am):
    """TennisExplorer's schedule writes `Paul T.` while the odds table on the
    same page writes `Paul Tommy` -- surname first. Both readings are kept so
    either source resolves without hardcoding an order per feed."""
    assert ("sinner", "j") in am.name_keys("Jannik Sinner")
    assert ("paul", "t") in am.name_keys("Paul Tommy")
    assert ("auger aliassime", "f") in am.name_keys("Felix Auger Aliassime")


def test_name_keys_strips_accents(am):
    assert any(last == "moller" for last, _ in am.name_keys("Möller H."))


def test_resolve_bare_surname(am):
    assert am.resolve_name("Sinner", ROSTER) == "Sinner J."
    assert am.resolve_name("alcaraz", ROSTER) == "Alcaraz C."


def test_resolve_across_naming_conventions(am):
    # Our roster spelling -> Tennis Abstract spelling and back.
    assert am.resolve_name("Sinner J.", TA_NAMES) == "Jannik Sinner"
    assert am.resolve_name("Jannik Sinner", ROSTER) == "Sinner J."
    assert am.resolve_name("Auger Aliassime F.", TA_NAMES) == "Felix Auger Aliassime"


def test_ambiguous_surname_returns_none_rather_than_guessing(am):
    """Two Zverevs: picking one silently would put the wrong player's stats
    in the briefing, so an initial-less query must fail loudly instead."""
    assert am.resolve_name("Zverev", ROSTER) is None
    # With an initial it resolves cleanly.
    assert am.resolve_name("Zverev A.", ROSTER) == "Zverev A."
    assert am.resolve_name("Mischa Zverev", ROSTER) == "Zverev M."


def test_unknown_player_returns_none(am):
    assert am.resolve_name("Federer", ROSTER) is None
    assert am.resolve_name("", ROSTER) is None


def test_wrong_initial_falls_back_to_unique_surname(am):
    """A typo'd initial still resolves when only one player has that
    surname -- better than failing on 'Sinner K.'."""
    assert am.resolve_name("Sinner K.", ROSTER) == "Sinner J."
    # But never when the surname itself is ambiguous.
    assert am.resolve_name("Zverev Q.", ROSTER) is None
