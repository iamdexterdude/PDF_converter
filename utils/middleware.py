"""Aiogram middlewares: per-user rate limiting and context injection."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from utils.session import session_manager

log = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Drops events that arrive faster than `rate` seconds apart per user."""

    def __init__(self, rate: float = 0.5) -> None:
        self.rate = rate
        self._last_seen: Dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        # Never rate-limit media uploads — albums arrive as a burst, and the
        # rate limiter would drop everything past the first one.
        if isinstance(event, Message) and (event.photo or event.document or event.media_group_id):
            return await handler(event, data)

        now = time.monotonic()
        elapsed = now - self._last_seen[user.id]
        if elapsed < self.rate:
            # Silently swallow rapid duplicate events (button spam)
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("⏳ Slow down a sec…")
                except Exception:  # noqa: BLE001
                    pass
            return None

        self._last_seen[user.id] = now
        return await handler(event, data)


class UserContextMiddleware(BaseMiddleware):
    """Injects the user's Session into handler kwargs as `session`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            data["session"] = await session_manager.get(user.id)
        return await handler(event, data)