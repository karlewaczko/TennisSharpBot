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


def test_daily_digest_scheduled_when_chat_id_set(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123456:fake-token-for-tests")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "42")
    app = build_application()
    assert len(app.job_queue.jobs()) == 1


def test_no_daily_digest_without_chat_id(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123456:fake-token-for-tests")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    app = build_application()
    assert len(app.job_queue.jobs()) == 0
