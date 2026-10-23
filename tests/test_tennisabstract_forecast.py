"""Tennis Abstract's /current/ forecast pages, on a trimmed copy of the real
2026 ATP Lyon page (title plus the script variables the parser reads)."""
from pathlib import Path

import pytest

from tennissharp.data import tennisabstract_forecast as taf

FIXTURE = Path(__file__).parent / "fixtures" / "tennisabstract_forecast_sample.html"


@pytest.fixture(scope="module")
def page():
    return FIXTURE.read_text(encoding="utf-8")


def test_names_lose_seed_entry_and_country(page):
    assert taf.clean_name("(1)<a href=\"x\">Flavio Cobolli</a> (ITA)") == "Flavio Cobolli"
    assert taf.clean_name("(WC) Stan Wawrinka (SUI)") == "Stan Wawrinka"
    assert taf.clean_name("(Q)Kyrian Jacquet (FRA)") == "Kyrian Jacquet"
    assert taf.clean_name("Bye") == "Bye"


def test_projection_reads_rounds_and_probabilities(page):
    rounds, probs = taf.parse_projection(taf._var(page, "projCurrent"))
    assert rounds == ["SF", "F", "W"]
    assert probs["Flavio Cobolli"] == {"SF": 0.389, "F": 0.216, "W": 0.091}
    assert probs["Brandon Nakashima"]["SF"] == pytest.approx(0.611)


def test_upcoming_pairings_carry_round_and_head_to_head(page):
    up = taf.parse_upcoming(taf._var(page, "upcomingSingles"))
    assert up[0] == {"round": "QF", "player_a": "Flavio Cobolli", "player_b": "Brandon Nakashima",
                     "h2h_a": 0, "h2h_b": 1}
    assert [u["player_a"] for u in up] == ["Flavio Cobolli", "Luca Van Assche",
                                           "Corentin Moutet", "Daniel Altmaier"]


def test_match_probability_is_the_next_round_figure_normalised(page):
    event = taf.parse_event_page(page)
    assert event["tournament"] == "ATP Lyon" and event["year"] == 2026
    by = {(m["player_a"], m["player_b"]): m for m in event["matches"]}
    m = by[("Daniel Altmaier", "Taylor Fritz")]
    assert m["p_a"] == pytest.approx(0.206 / (0.206 + 0.794), abs=1e-4)
    assert m["next_round"] == "SF"
    assert m["title_b"] == pytest.approx(0.241)


def test_pairing_without_matching_projection_has_no_probability():
    html = ("<title>Tennis Abstract: 2026 ATP Test Results and Forecast</title>"
            "<script>var projCurrent = '<table><tr><td>Player</td><td></td><td>SF</td></tr>"
            "<tr><td>A B</td><td></td><td>60.0%</td></tr></table>';"
            "var upcomingSingles = 'QF: A B (XXX) vs C D (YYY)';</script>")
    event = taf.parse_event_page(html)
    assert event["matches"][0]["p_a"] is None


def test_front_page_links_are_filtered_by_year():
    home = ('<a href="https://www.tennisabstract.com/current/2025WimbledonMenForecast.html">x</a>'
            '<a href="https://www.tennisabstract.com/current/2026ATPLyon.html">y</a>'
            '<a href="https://www.tennisabstract.com/current/2026ATPLyon.html">y</a>')
    assert taf.list_current_events(home, 2026) == ["https://www.tennisabstract.com/current/2026ATPLyon.html"]


def test_fetch_groups_rows_per_pairing(monkeypatch, page):
    class Resp:
        def __init__(self, text):
            self.text = text
        def raise_for_status(self):
            pass

    class Http:
        def get(self, url, headers=None, timeout=None):
            if url == taf.HOME_URL:
                return Resp('<a href="https://www.tennisabstract.com/current/2026ATPLyon.html">x</a>')
            return Resp(page)

    df = taf.fetch_forecasts(year=2026, session=Http(), sleep=lambda s: None)
    assert len(df) == 4
    assert df["p_a"].notna().all()
    assert df.iloc[0]["tournament"] == "ATP Lyon"
