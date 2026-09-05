"""Retry behaviour for the season-file download.

The season spreadsheets come over plain HTTP from a small site and time out
often enough to matter. With no local cache -- a fresh checkout, or CI --
a single timeout used to drop a whole season out of the training history
behind nothing but a WARNING line.
"""
import pytest
import requests

from tennissharp.data import odds_history as oh


class _Resp:
    def __init__(self, content=b"xlsx", status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code}")
            err.response = self
            raise err


def test_a_transient_timeout_is_retried(monkeypatch):
    calls = []

    def flaky(url, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise requests.Timeout("read timed out")
        return _Resp()

    monkeypatch.setattr(oh.requests, "get", flaky)
    assert oh._fetch_season_file("http://x/atp_2010.xlsx", sleep=lambda _: None) == b"xlsx"
    assert len(calls) == 3


def test_it_gives_up_after_the_configured_attempts(monkeypatch):
    calls = []

    def always_times_out(url, timeout):
        calls.append(url)
        raise requests.Timeout("read timed out")

    monkeypatch.setattr(oh.requests, "get", always_times_out)
    with pytest.raises(requests.Timeout):
        oh._fetch_season_file("http://x/atp_2010.xlsx", sleep=lambda _: None)
    assert len(calls) == oh.DOWNLOAD_ATTEMPTS


def test_a_missing_season_is_not_retried(monkeypatch):
    """A 404 is an answer -- that season does not exist. Retrying it spends
    three times as long reaching the same conclusion."""
    calls = []

    def missing(url, timeout):
        calls.append(url)
        return _Resp(status=404)

    monkeypatch.setattr(oh.requests, "get", missing)
    with pytest.raises(requests.HTTPError):
        oh._fetch_season_file("http://x/atp_1999.xlsx", sleep=lambda _: None)
    assert len(calls) == 1


def test_backoff_grows_between_attempts(monkeypatch):
    waits = []
    monkeypatch.setattr(oh.requests, "get",
                        lambda url, timeout: (_ for _ in ()).throw(requests.Timeout("x")))
    with pytest.raises(requests.Timeout):
        oh._fetch_season_file("http://x", sleep=waits.append)
    # One wait fewer than attempts -- no point sleeping after the last try.
    assert waits == [oh.RETRY_BACKOFF * (i + 1) for i in range(oh.DOWNLOAD_ATTEMPTS - 1)]


def test_the_timeout_is_generous_enough_for_a_multi_megabyte_file():
    assert oh.DOWNLOAD_TIMEOUT >= 60
