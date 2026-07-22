from pathlib import Path

from tennissharp.data.tennisabstract import parse_elo_html, parse_surface_speed_html

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_elo_html_ranks_are_numeric_and_ordered():
    html = (FIXTURES / "atp_elo_ratings_sample.html").read_text(encoding="utf-8")
    df = parse_elo_html(html, "atp")
    assert len(df) > 100
    assert df["elo_rank"].dtype.kind in "if"  # int or float, never string
    # The table is already rank-ordered in the source page.
    ranks = df["elo_rank"].tolist()
    assert ranks == sorted(ranks)
    assert df.iloc[0]["player"] == "Jannik Sinner"
    assert df.iloc[0]["elo_rank"] == 1


def test_parse_elo_html_surface_columns_present():
    html = (FIXTURES / "atp_elo_ratings_sample.html").read_text(encoding="utf-8")
    df = parse_elo_html(html, "atp")
    for col in ("elo", "helo", "celo", "gelo", "peak_elo"):
        assert col in df.columns
        assert df[col].notna().any()


def test_parse_surface_speed_html():
    html = (FIXTURES / "atp_surface_speed_sample.html").read_text(encoding="utf-8")
    df = parse_surface_speed_html(html)
    assert len(df) > 10
    assert {"date", "tournament", "surface", "ace_pct", "surface_speed"} <= set(df.columns)
    # Ace% is stored as a 0-1 fraction, not a "16.5%" string.
    assert df["ace_pct"].between(0, 1).all()
    assert df["surface_speed"].dtype.kind == "f"
