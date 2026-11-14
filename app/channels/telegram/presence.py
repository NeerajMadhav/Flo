# app/channels/telegram/presence.py
"""Realtime chat presence — typing indicator while Flo thinks."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ChatAction


async def show_typing(update: Update) -> None:
    """Signal that Flo is listening / working (Telegram typing bubble)."""
    chat = update.effective_chat
    if chat is None:
        return
    try:
        await update.get_bot().send_chat_action(
            chat_id=chat.id, action=ChatAction.TYPING
        )
    except Exception:
        # Presence is best-effort; never block the turn.
        return
