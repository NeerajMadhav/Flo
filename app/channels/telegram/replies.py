# app/channels/telegram/replies.py
"""Reply helpers that respect turn cancel/supersede."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from telegram import Update

from app.channels.telegram.memory import remember_bot_reply
from app.core.turn_manager import TurnTicket, get_turn_manager
from app.utils.logger import get_logger, log_event

logger = get_logger("flo.telegram")

_ticket: ContextVar[TurnTicket | None] = ContextVar("flo_ticket", default=None)


@contextmanager
def bind_ticket(ticket: TurnTicket | None) -> Iterator[None]:
    token = _ticket.set(ticket)
    try:
        yield
    finally:
        _ticket.reset(token)


def current_ticket() -> TurnTicket | None:
    return _ticket.get()


async def send(update: Update, text: str, **kwargs) -> bool:
    """
    Send a Telegram reply if this turn is still active.
    Returns False when superseded (caller should stop work).
    """
    ticket = _ticket.get()
    if ticket is not None and not ticket.alive(get_turn_manager()):
        log_event(
            logger,
            "turn.reply_skipped",
            tg_id=ticket.tg_id,
            gen=ticket.gen,
        )
        return False
    msg = update.effective_message
    if not msg:
        return False
    await msg.reply_text(text, **kwargs)
    tg_id = str(update.effective_user.id) if update.effective_user else ""
    if tg_id:
        await remember_bot_reply(tg_id, text)
    return True
