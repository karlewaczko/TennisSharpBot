import datetime as dt
from pathlib import Path

from tennissharp.data.tennisexplorer import (
    day_for_offset, day_url, head_to_head_summary, parse_head_to_head_html, parse_matches_html,
    parse_odds_history_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_matches_html_extracts_pairs_with_odds():
    html = (FIXTURES / "tennisexplorer_matches_sample.html").read_text(encoding="utf-8")
    df = parse_matches_html(html)
    assert len(df) > 100
    for col in ("tournament", "player1", "player1_slug", "player2", "player2_slug", "match_id"):
        assert col in df.columns
        assert df[col].notna().all()
    # Most (not all -- some matches genuinely lack a market) rows should carry odds.
    assert df["odds1"].notna().mean() > 0.5


def test_parse_matches_html_pairs_do_not_duplicate_player1_as_player2():
    html = (FIXTURES / "tennisexplorer_matches_sample.html").read_text(encoding="utf-8")
    df = parse_matches_html(html)
    assert (df["player1"] != df["player2"]).all()


def test_parse_matches_html_extracts_final_scores_for_finished_matches():
    html = (FIXTURES / "tennisexplorer_matches_sample.html").read_text(encoding="utf-8")
    df = parse_matches_html(html)
    finished = df[df["score"].notna()]
    assert len(finished) > 50
    row = finished[(finished["player1"] == "Gaston H.") & (finished["player2"] == "Droguet T.")].iloc[0]
    assert row["score"] == "6-0 6-3"
    assert row["sets_won1"] == 2 and row["sets_won2"] == 0
    # Unfinished/future matches in the same fixture must stay unscored, not zeroed.
    unfinished = df[df["score"].isna()]
    assert len(unfinished) > 0
    assert unfinished["sets_won1"].isna().all()


_ODDS_HISTORY_SAMPLE_HTML = """
<table class="result " cellspacing="0">
<tbody>
<tr class="head"><td class="tl"> </td><td class="k1">Fritz Taylor</td><td class="k2">O'Connell Christopher</td></tr>
<tr class="one">
<td class="first tl"><a><span class="t">10Bet</span></a></td>
<td class="k1"><div class="odds-in odown">1.08<div class="odds-change-div"><table cellspacing="0">
<tr><td>19.08. 15:38</td><td class="bold">1.08</td><td class="diff-down">-0.02</td></tr>
<tr><td colspan="3" class="title">Opening odds</td></tr>
<tr><td>18.08. 21:20</td><td class="bold">1.11</td><td class="diff-down">&nbsp</td></tr>
</table></div></div></td>
<td class="k2"><div class="odds-in oup">7.00<div class="odds-change-div"><table cellspacing="0">
<tr><td>19.08. 06:23</td><td class="bold">7.00</td><td class="diff-up">+0.50</td></tr>
<tr><td colspan="3" class="title">Opening odds</td></tr>
<tr><td>18.08. 21:20</td><td class="bold">6.00</td><td class="diff-down">&nbsp</td></tr>
</table></div></div></td>
</tr>
</tbody>
</table>
"""


def test_parse_odds_history_html_extracts_bookmaker_timeline():
    df = parse_odds_history_html(_ODDS_HISTORY_SAMPLE_HTML, reference_date=dt.date(2026, 8, 19))
    assert len(df) == 4
    assert set(df["bookmaker"]) == {"10Bet"}
    assert set(df["player"]) == {"Fritz Taylor", "O'Connell Christopher"}

    fritz = df[df["player"] == "Fritz Taylor"].sort_values("timestamp")
    assert list(fritz["odds"]) == [1.11, 1.08]  # opening first, then latest
    assert fritz.iloc[0]["is_opening"] and not fritz.iloc[1]["is_opening"]
    assert fritz.iloc[0]["timestamp"] == dt.datetime(2026, 8, 18, 21, 20)


def test_parse_odds_history_html_missing_table_returns_empty():
    assert parse_odds_history_html("<html><body>no odds here</body></html>").empty


def test_parse_head_to_head_html_and_summary():
    html = (FIXTURES / "tennisexplorer_h2h_sample.html").read_text(encoding="utf-8")
    df = parse_head_to_head_html(html)
    assert len(df) == 30  # 15 historical matches, 2 rows each
    assert {"year", "tournament", "player", "sets_won", "round"} <= set(df.columns)

    sinner_wins, zverev_wins = head_to_head_summary(df, "Sinner J.", "Zverev A.")
    assert sinner_wins == 11
    assert zverev_wins == 4
    # Order shouldn't matter beyond which slot each count lands in.
    zverev_wins2, sinner_wins2 = head_to_head_summary(df, "Zverev A.", "Sinner J.")
    assert (sinner_wins2, zverev_wins2) == (sinner_wins, zverev_wins)


def test_day_url_spells_out_the_full_date():
    """The site's `day` parameter is a day of the month, not an offset.
    Passing the offset straight through returned the 1st of the month for
    `day_offset=1`, filling the upcoming-matches file with old results."""
    url = day_url(1, today=dt.date(2026, 8, 22))
    assert "year=2026" in url and "month=08" in url and "day=23" in url


def test_day_url_crosses_month_and_year_boundaries():
    assert "year=2026&month=09&day=01" in day_url(1, today=dt.date(2026, 8, 31))
    assert "year=2027&month=01&day=01" in day_url(1, today=dt.date(2026, 12, 31))
    assert "year=2026&month=07&day=31" in day_url(-1, today=dt.date(2026, 8, 1))


def test_day_url_zero_pads_so_the_site_reads_the_date():
    url = day_url(0, today=dt.date(2026, 3, 5))
    assert "month=03" in url and "day=05" in url


def test_day_for_offset_is_the_calendar_date():
    assert day_for_offset(2, today=dt.date(2026, 8, 22)) == dt.date(2026, 8, 24)
    assert day_for_offset(0, today=dt.date(2026, 8, 22)) == dt.date(2026, 8, 22)


def test_a_blank_day_still_has_the_columns():
    """A date the site has not filled in yet parses to no rows. Returning a
    frame with no columns makes the first `df["score"]` raise instead of
    selecting nothing -- fetching three days ahead hits this routinely."""
    df = parse_matches_html("<html><body>nothing scheduled</body></html>")
    assert df.empty
    for col in ("score", "sets_won1", "sets_won2", "odds1", "match_id", "tournament"):
        assert col in df.columns
    assert df["score"].notna().sum() == 0


def test_a_blank_day_survives_a_concat_with_a_real_one():
    import pandas as pd
    real = parse_matches_html(
        (FIXTURES / "tennisexplorer_matches_sample.html").read_text(encoding="utf-8"))
    blank = parse_matches_html("<html></html>")
    both = pd.concat([real, blank], ignore_index=True)
    assert len(both) == len(real)
    assert list(both.columns) == list(real.columns)
