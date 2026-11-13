"""The sharp-move alert's logic: when a rise counts, once per side, and the
lowest bet365 price still worth taking."""
from tennissharp import sharp_moves as sm


def test_a_rise_of_three_points_within_half_an_hour_is_a_move_once():
    w = sm.Watch()
    assert w.update("Kalshi|g|LAL", "g|LAL", 0, 0.50) is None
    assert w.update("Kalshi|g|LAL", "g|LAL", 900, 0.52) is None           # not half an hour of history yet
    move = w.update("Kalshi|g|LAL", "g|LAL", 1800, 0.53)
    assert move and move["before"] == 0.50 and move["now"] == 0.53
    assert w.update("Kalshi|g|LAL", "g|LAL", 1860, 0.56) is None          # the same side: once in three hours
    assert w.update("Polymarket|g|LAL", "g|LAL", 0, 0.50) is None
    assert w.update("Polymarket|g|LAL", "g|LAL", 1800, 0.55) is None      # nor from the other venue
    again = w.update("Kalshi|g|LAL", "g|LAL", 1800 + 3 * 3600, 0.60)          # three hours on it may fire again
    assert again and again["before"] == 0.56


def test_a_fall_or_a_slow_drift_is_no_move():
    w = sm.Watch()
    for t, p in ((0, 0.60), (1800, 0.55)):
        assert w.update("Polymarket|g|BOS", "g|BOS", t, p) is None        # the other side's rise is its own key
    for t, p in ((0, 0.40), (1800, 0.42), (3600, 0.44), (5400, 0.46)):
        assert w.update("Kalshi|h|NYK", "h|NYK", t, p) is None            # 2 points per half hour


def test_the_lowest_price_worth_taking():
    assert sm.min_odds(0.59) == 1.73                                      # 1.02 / 0.59 = 1.7288, rounded up
    assert sm.min_odds(0.5, margin=0.0) == 2.0
    assert sm.min_odds(0.0) is None and sm.min_odds(1.0) is None


def test_the_message_names_the_jump_and_the_price_to_beat():
    text, fair, least = sm.alert_text("🏀 NBA", "Lakers – Celtics", "14.11. 01:30", "Lakers", "Kalshi", 0.55, 0.59,
                                      {"Polymarket": 0.57}, "https://polymarket.com/event/nba-lal-bos-2026-11-13")
    assert "Kalshi: Lakers Quote 1,82 → 1,69 in 30 Min." in text and "Polymarket jetzt Quote 1,75" in text
    assert "%" not in text                                                # odds only, no chances
    assert fair == 0.58 and least == sm.min_odds(0.58) and f"ab Quote {least:.2f}".replace(".", ",") in text
