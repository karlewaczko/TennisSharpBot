from pathlib import Path

from tennissharp.data.tennisexplorer import (
    head_to_head_summary, parse_head_to_head_html, parse_matches_html,
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
