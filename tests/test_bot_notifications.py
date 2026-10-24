import pandas as pd

from tennissharp.bot.notifications import bet_key, filter_new_bets, mark_seen, prune_past


def _bets(rows):
    return pd.DataFrame(rows, columns=["player", "opponent", "bookmaker", "commence_time",
                                        "edge", "odds"])


def test_filter_new_bets_returns_everything_when_nothing_seen():
    df = _bets([("Djokovic N.", "Nadal R.", "Pinnacle", "2026-08-01T12:00:00Z", 0.05, 2.1)])
    result = filter_new_bets(df, seen=set())
    assert len(result) == 1


def test_filter_new_bets_excludes_already_seen():
    df = _bets([
        ("Djokovic N.", "Nadal R.", "Pinnacle", "2026-08-01T12:00:00Z", 0.05, 2.1),
        ("Sinner J.", "Alcaraz C.", "bet365", "2026-08-01T14:00:00Z", 0.04, 1.9),
    ])
    seen = {bet_key("Djokovic N.", "Nadal R.", "Pinnacle", "2026-08-01T12:00:00Z")}
    result = filter_new_bets(df, seen)
    assert len(result) == 1
    assert result.iloc[0]["player"] == "Sinner J."


def test_mark_seen_then_filter_excludes_it():
    df = _bets([("Djokovic N.", "Nadal R.", "Pinnacle", "2026-08-01T12:00:00Z", 0.05, 2.1)])
    seen = set()
    mark_seen(df, seen)
    assert filter_new_bets(df, seen).empty


def test_same_matchup_different_bookmaker_is_a_distinct_key():
    # Same players, same time, but a different book -- should not be deduped
    # against each other since they're different bets you could each place.
    df1 = _bets([("A", "B", "Pinnacle", "2026-08-01T12:00:00Z", 0.05, 2.1)])
    df2 = _bets([("A", "B", "bet365", "2026-08-01T12:00:00Z", 0.05, 2.1)])
    seen = set()
    mark_seen(df1, seen)
    assert not filter_new_bets(df2, seen).empty


def test_prune_past_drops_matches_that_already_started():
    now = pd.Timestamp("2026-08-01T12:00:00")
    seen = {
        bet_key("A", "B", "Pinnacle", "2026-08-01T10:00:00Z"),  # in the past
        bet_key("C", "D", "Pinnacle", "2026-08-02T10:00:00Z"),  # in the future
    }
    kept = prune_past(seen, now)
    assert kept == {bet_key("C", "D", "Pinnacle", "2026-08-02T10:00:00Z")}


def test_prune_past_drops_unparseable_timestamps_rather_than_keeping_forever():
    seen = {bet_key("A", "B", "Pinnacle", "not-a-real-timestamp")}
    kept = prune_past(seen, pd.Timestamp("2026-08-01"))
    assert kept == set()


def test_filter_new_bets_on_empty_dataframe():
    df = pd.DataFrame(columns=["player", "opponent", "bookmaker", "commence_time"])
    assert filter_new_bets(df, seen=set()).empty
