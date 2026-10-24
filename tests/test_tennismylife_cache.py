"""The TennisMyLife cache: closed seasons stay, the running season expires."""
import datetime as dt
import os

import pytest
import requests

from tennissharp import config
from tennissharp.data import tennismylife as tml


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    calls = []

    def fake_fetch(url, sleep=None):
        calls.append(url)
        return b"tourney_date,winner_name\n"

    monkeypatch.setattr(tml, "_fetch_season_file", fake_fetch)
    return tmp_path, calls


def _cache(tmp_path, key, year, age_hours, now):
    path = tmp_path / "tennismylife" / tml._local_name(key, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"old")
    mtime = now - age_hours * 3600
    os.utime(path, (mtime, mtime))
    return path


TODAY = dt.date(2026, 10, 24)
NOW = 1_792_800_000.0


def test_a_closed_season_is_never_refetched(raw):
    tmp_path, calls = raw
    path = _cache(tmp_path, "atp", 2025, age_hours=24 * 300, now=NOW)
    assert tml.download_season("atp", 2025, today=TODAY, now=NOW) == path
    assert calls == []


def test_the_running_season_expires(raw):
    """The bug this fixes: the 2026 file was loaded once and never again."""
    tmp_path, calls = raw
    path = _cache(tmp_path, "atp", 2026, age_hours=30, now=NOW)
    assert tml.download_season("atp", 2026, today=TODAY, now=NOW) == path
    assert len(calls) == 1
    assert path.read_bytes().startswith(b"tourney_date")


def test_a_fresh_copy_of_the_running_season_is_reused(raw):
    tmp_path, calls = raw
    _cache(tmp_path, "wta", 2026, age_hours=1, now=NOW)
    tml.download_season("wta", 2026, today=TODAY, now=NOW)
    assert calls == []


def test_a_failed_refresh_keeps_the_stale_copy(raw, monkeypatch):
    tmp_path, _ = raw
    path = _cache(tmp_path, "challenger", 2026, age_hours=48, now=NOW)

    def down(url, sleep=None):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(tml, "_fetch_season_file", down)
    assert tml.download_season("challenger", 2026, today=TODAY, now=NOW) == path
    assert path.read_bytes() == b"old"


def test_no_cache_and_no_network_is_none(raw, monkeypatch):
    monkeypatch.setattr(tml, "_fetch_season_file",
                        lambda url, sleep=None: (_ for _ in ()).throw(requests.HTTPError("404")))
    assert tml.download_season("atp", 2027, today=TODAY, now=NOW) is None


def test_january_still_refreshes_the_season_just_closed():
    assert tml.is_running_season(2025, dt.date(2026, 1, 10))
    assert not tml.is_running_season(2025, dt.date(2026, 2, 1))
    assert tml.is_running_season(2026, dt.date(2026, 10, 24))
