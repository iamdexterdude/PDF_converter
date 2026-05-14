"""
PDF Toolkit Bot — a professional all-in-one PDF utility for Telegram.

Features:
    • Images → PDF (with page size, orientation, fit mode, margins, quality)
    • Merge / split / compress PDFs
    • Rotate pages, add password, add watermark
    • PDF → images, OCR (make searchable)
    • Metadata editor
    • Per-user session state, rate limiting, async I/O

Run:
    export BOT_TOKEN="123:abc"
    python bot.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from config import settings
from handlers import (
    common,
    images_to_pdf,
    pdf_tools,
    errors,
)
from utils.middleware import RateLimitMiddleware, UserContextMiddleware


def setup_logging() -> None:
    """Configure logging with rotation. Console + file."""
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)

    # Avoid duplicate handlers on reload
    root.handlers.clear()

    # Stdout
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Rotating file (10MB x 5 files) — best-effort, skip if path not writable
    try:
        file_handler = RotatingFileHandler(
            settings.LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as e:
        logging.warning("File logging disabled: %s", e)

    # Quiet noisy libs
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


async def on_startup(bot: Bot) -> None:
    me = await bot.get_me()
    logging.info("Bot started: @%s (id=%d)", me.username, me.id)


async def on_shutdown(bot: Bot) -> None:
    logging.info("Shutting down — closing bot session")
    await bot.session.close()


async def _health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def _start_health_server(port: int) -> web.AppRunner:
    """Tiny HTTP server so platforms requiring an open port are satisfied,
    and so an uptime-pinger can keep the service awake on Render's free tier."""
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("Health server listening on :%d", port)
    return runner


async def main() -> None:
    setup_logging()
    settings.ensure_dirs()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares — order matters: context first, then rate limiting
    dp.message.middleware(UserContextMiddleware())
    dp.callback_query.middleware(UserContextMiddleware())
    dp.message.middleware(RateLimitMiddleware(rate=settings.RATE_LIMIT))
    dp.callback_query.middleware(RateLimitMiddleware(rate=settings.RATE_LIMIT))

    # Routers — order = priority for matching
    dp.include_routers(
        common.router,
        images_to_pdf.router,
        pdf_tools.router,
        errors.router,  # catch-all last
    )

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # If $PORT is set (Render Web Service / Railway / Heroku-style), expose
    # a tiny HTTP health endpoint. Locally — when PORT is unset — no server runs.
    health_runner: web.AppRunner | None = None
    port_str = os.getenv("PORT")
    if port_str:
        try:
            health_runner = await _start_health_server(int(port_str))
        except Exception as e:  # noqa: BLE001
            logging.exception("Health server failed to start: %s", e)

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logging.info("Signal received — initiating shutdown")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    polling_task = asyncio.create_task(dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()))
    stop_task = asyncio.create_task(stop_event.wait())

    done, pending = await asyncio.wait(
        {polling_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()
    await dp.stop_polling()
    if health_runner is not None:
        await health_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
