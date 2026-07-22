import pandas as pd

from tennissharp.tourney_matching import (
    build_surface_speed_index, lookup_surface_speed, normalize_tourney_name,
)


def test_normalize_strips_generic_words_and_numbers():
    assert normalize_tourney_name("ATP Montpellier") == "montpellier"
    assert normalize_tourney_name("Miami Masters") == "miami"
    assert normalize_tourney_name("Adelaide International 1") == "adelaide"


def test_build_and_lookup_exact_match():
    speed_df = pd.DataFrame({
        "date": pd.to_datetime(["2024-08-26"]),
        "tournament": ["US Open"],
        "surface": ["Hard"],
        "ace_pct": [0.12],
        "surface_speed": [1.05],
    })
    index = build_surface_speed_index(speed_df)
    assert lookup_surface_speed(index, 2024, "US Open") == 1.05


def test_lookup_falls_back_to_default_when_unmatched():
    index = build_surface_speed_index(pd.DataFrame({
        "date": pd.to_datetime(["2024-08-26"]),
        "tournament": ["US Open"],
        "surface": ["Hard"],
        "ace_pct": [0.12],
        "surface_speed": [1.05],
    }))
    assert lookup_surface_speed(index, 2024, "Some Obscure Challenger") == 1.0
    assert lookup_surface_speed(index, 1999, "US Open") == 1.0  # wrong season


def test_lookup_substring_fallback_handles_naming_drift():
    index = build_surface_speed_index(pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01"]),
        "tournament": ["Australian Open"],
        "surface": ["Hard"],
        "ace_pct": [0.1],
        "surface_speed": [0.95],
    }))
    assert lookup_surface_speed(index, 2024, "Australian Open Qualifying") == 0.95
