# app/channels/telegram/handlers/fallback.py
"""Unknown / greeting / non-text fallbacks."""

from __future__ import annotations

from telegram import Update

from app.channels.telegram.memory import remember_bot_reply
from app.utils.guardrails import GuardrailCode, bot_name, explain


async def handle_unknown(update: Update) -> None:
    tg_id = str(update.effective_user.id)
    reply = explain(GuardrailCode.UNKNOWN)
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def handle_greeting(update: Update, name: str | None = None) -> None:
    tg_id = str(update.effective_user.id)
    who = name or "there"
    reply = f"Hey {who}! I'm {bot_name()} 👋 What would you like to log?"
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def handle_non_text(update: Update) -> None:
    tg_id = str(update.effective_user.id)
    reply = explain(GuardrailCode.NON_TEXT)
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)
