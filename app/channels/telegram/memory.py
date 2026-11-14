# app/channels/telegram/memory.py
"""Persist bot replies into rolling conversation context for NLP follow-ups."""

from __future__ import annotations

from app.core.database import AsyncSessionLocal
from app.services.state_service import StateService
from app.utils.logger import get_logger, log_event

logger = get_logger("flo.memory")


async def remember_bot_reply(telegram_user_id: str, text: str) -> None:
    """
    Store what Riruru just said so the next user message has that context.

    Never raises — the Telegram reply was already sent; failing memory must not
    trigger a second "something went wrong" message to the user.
    """
    if not text or not telegram_user_id:
        return
    try:
        async with AsyncSessionLocal() as session:
            await StateService(session).append_turn(telegram_user_id, "bot", text)
    except Exception as e:
        log_event(
            logger,
            "memory.bot_reply_failed",
            error=str(e),
            telegram_user_id=telegram_user_id,
        )
