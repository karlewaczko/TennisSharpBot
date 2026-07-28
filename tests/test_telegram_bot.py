import pytest

from tennissharp import config
from tennissharp.bot.telegram_bot import build_application


def test_build_application_requires_token(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        build_application()


def test_build_application_registers_all_commands(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123456:fake-token-for-tests")
    app = build_application()
    registered = {h.callback.__name__ for h in app.handlers[0]}
    assert registered == {"start", "help_command", "rankings", "surface", "upcoming", "h2h", "valuebets"}


def _job_names(app) -> set[str]:
    return {j.callback.__name__ for j in app.job_queue.jobs()}


def test_daily_digest_scheduled_when_chat_id_set(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123456:fake-token-for-tests")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(config, "ODDS_API_KEY", "")
    monkeypatch.setattr(config, "TELEGRAM_VALUEBETS_INTERVAL_MINUTES", 0)
    app = build_application()
    assert _job_names(app) == {"_daily_digest"}


def test_no_daily_digest_without_chat_id(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123456:fake-token-for-tests")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "ODDS_API_KEY", "")
    monkeypatch.setattr(config, "TELEGRAM_VALUEBETS_INTERVAL_MINUTES", 0)
    app = build_application()
    assert len(app.job_queue.jobs()) == 0


def test_value_bet_scan_scheduled_when_fully_configured(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123456:fake-token-for-tests")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(config, "ODDS_API_KEY", "fake-odds-key")
    monkeypatch.setattr(config, "TELEGRAM_VALUEBETS_INTERVAL_MINUTES", 180)
    app = build_application()
    assert _job_names(app) == {"_daily_digest", "_scan_value_bets"}


def test_value_bet_scan_not_scheduled_without_odds_api_key(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123456:fake-token-for-tests")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(config, "ODDS_API_KEY", "")
    monkeypatch.setattr(config, "TELEGRAM_VALUEBETS_INTERVAL_MINUTES", 180)
    app = build_application()
    assert "_scan_value_bets" not in _job_names(app)


def test_value_bet_scan_not_scheduled_when_interval_is_zero(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123456:fake-token-for-tests")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(config, "ODDS_API_KEY", "fake-odds-key")
    monkeypatch.setattr(config, "TELEGRAM_VALUEBETS_INTERVAL_MINUTES", 0)
    app = build_application()
    assert "_scan_value_bets" not in _job_names(app)
