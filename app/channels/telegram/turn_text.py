# app/channels/telegram/turn_text.py
"""Per-task text override so merged/queued turns use the right user string."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from telegram import Update

_override: ContextVar[str | None] = ContextVar("flo_turn_text", default=None)


@contextmanager
def use_turn_text(text: str) -> Iterator[None]:
    token = _override.set(text)
    try:
        yield
    finally:
        _override.reset(token)


def user_text(update: Update) -> str:
    """User message for this turn (override if set, else Telegram text)."""
    ov = _override.get()
    if ov is not None:
        return ov
    msg = update.effective_message
    return ((msg.text if msg else None) or "").strip()
