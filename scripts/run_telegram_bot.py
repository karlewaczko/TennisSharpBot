#!/usr/bin/env python3
"""Start the Telegram bot (long-polling). Runs until killed (Ctrl+C).

Requires TELEGRAM_BOT_TOKEN in config/.env -- see README's "Telegram Bot &
REST API" section for BotFather setup. Run scripts/update_data.py at least
once first so there's data to answer commands with.
"""
import _bootstrap  # noqa: F401

from tennissharp.bot.telegram_bot import main

if __name__ == "__main__":
    main()
