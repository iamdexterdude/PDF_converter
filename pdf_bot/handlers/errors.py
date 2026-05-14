"""Catch-all error and fallback router."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent, Message

from utils.keyboards import main_menu

router = Router(name="errors")
log = logging.getLogger(__name__)


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    log.exception("Unhandled error: %s", event.exception, exc_info=event.exception)
    upd = event.update
    try:
        if upd.message:
            await upd.message.answer(
                "❌ Something went wrong on my side. Try /start to reset."
            )
        elif upd.callback_query:
            await upd.callback_query.answer(
                "Something went wrong — try /start", show_alert=True
            )
    except Exception:  # noqa: BLE001
        pass
    return True


# Fallback for any unhandled message — keep last
@router.message()
async def fallback(msg: Message) -> None:
    await msg.answer(
        "I'm not sure what you mean. Pick a tool from the menu, or send /help.",
        reply_markup=main_menu(),
    )
