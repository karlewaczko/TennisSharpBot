"""Telegram bot front end for the TennisSharpBot data/model pipeline.

All commands are read-only queries against the processed data files that
`scripts/update_data.py` produces -- run that at least once (and keep the
scheduled GitHub Actions workflow going) before starting this bot.

Blocking I/O (scraping, model loading) is offloaded to a thread executor so
one slow request (e.g. /h2h, which hits TennisExplorer live) doesn't stall
the bot for other users/chats.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from tennissharp import config, service
from tennissharp.bot import formatting

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "<b>TennisSharpBot</b>\n"
    "/rankings [atp|wta] [ta|own] -- Elo-Rangliste (Standard: atp, Tennis Abstract)\n"
    "/surface [Turniername] -- Surface-Speed-Rating; ohne Namen: schnellste Turniere der Saison\n"
    "/upcoming [atp|wta] -- anstehende Spiele + Quoten\n"
    "/h2h Spieler1 Spieler2 -- Head-to-Head (nur Spieler aus dem aktuellen Spielplan)\n"
    "/valuebets -- aktuelle Value Bets (braucht ODDS_API_KEY auf dem Server)\n\n"
    + formatting.DISCLAIMER
)


async def _run_blocking(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def _reply(update: Update, text: str) -> None:
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, HELP_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, HELP_TEXT)


async def rankings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tour = context.args[0].lower() if len(context.args) >= 1 else "atp"
    source = context.args[1].lower() if len(context.args) >= 2 else "ta"
    try:
        df = await _run_blocking(service.get_rankings, tour, 10, source)
        await _reply(update, formatting.format_rankings(df, tour, source))
    except service.DataNotReadyError as exc:
        await _reply(update, formatting.format_error(str(exc)))


async def surface(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tournament = " ".join(context.args) if context.args else None
    try:
        df = await _run_blocking(service.get_surface_speed, tournament, 10)
        await _reply(update, formatting.format_surface_speed(df, tournament))
    except service.DataNotReadyError as exc:
        await _reply(update, formatting.format_error(str(exc)))


async def upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tour = context.args[0].lower() if context.args else None
    try:
        df = await _run_blocking(service.get_upcoming_matches, tour, 15)
        await _reply(update, formatting.format_upcoming(df, tour))
    except service.DataNotReadyError as exc:
        await _reply(update, formatting.format_error(str(exc)))


async def h2h(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await _reply(update, formatting.format_error("Nutzung: /h2h Spieler1 Spieler2"))
        return
    player1, player2 = context.args[0], context.args[1]
    try:
        result = await _run_blocking(service.get_head_to_head, player1, player2)
        await _reply(update, formatting.format_h2h(result))
    except (service.DataNotReadyError, ValueError) as exc:
        await _reply(update, formatting.format_error(str(exc)))


async def valuebets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.ODDS_API_KEY:
        await _reply(update, formatting.format_error(
            "ODDS_API_KEY ist auf dem Server nicht gesetzt -- /valuebets braucht einen "
            "eigenen Schlüssel von https://the-odds-api.com"))
        return
    await update.message.reply_text("Suche Value Bets, einen Moment...")
    try:
        df = await _run_blocking(service.get_value_bets)
        await _reply(update, formatting.format_value_bets(df))
    except (service.DataNotReadyError, RuntimeError) as exc:
        await _reply(update, formatting.format_error(str(exc)))


async def _daily_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.TELEGRAM_CHAT_ID:
        return
    try:
        atp = await _run_blocking(service.get_rankings, "atp", 5, "ta")
        wta = await _run_blocking(service.get_rankings, "wta", 5, "ta")
        text = (formatting.format_rankings(atp, "atp", "ta") + "\n\n"
                + formatting.format_rankings(wta, "wta", "ta"))
        await context.bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=text,
                                        parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("Daily digest failed")


def build_application() -> Application:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Create a bot with @BotFather on Telegram "
            "and put the token in config/.env (see config/settings.example.env)."
        )
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rankings", rankings))
    app.add_handler(CommandHandler("surface", surface))
    app.add_handler(CommandHandler("upcoming", upcoming))
    app.add_handler(CommandHandler("h2h", h2h))
    app.add_handler(CommandHandler("valuebets", valuebets))

    if app.job_queue is not None and config.TELEGRAM_CHAT_ID:
        app.job_queue.run_daily(
            _daily_digest,
            time=dt.time(hour=config.TELEGRAM_DIGEST_HOUR_UTC, tzinfo=dt.timezone.utc),
        )
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = build_application()
    logger.info("Starting Telegram bot (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
