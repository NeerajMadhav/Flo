# app/channels/telegram/handlers/fallback.py
"""Unknown / greeting / non-text fallbacks."""

from __future__ import annotations

from telegram import Update

from app.utils.guardrails import GuardrailCode, bot_name, explain


async def handle_unknown(update: Update) -> None:
    await update.effective_message.reply_text(explain(GuardrailCode.UNKNOWN))


async def handle_greeting(update: Update, name: str | None = None) -> None:
    who = name or "there"
    await update.effective_message.reply_text(
        f"Hey {who}! I'm {bot_name()} 👋 What would you like to log?"
    )


async def handle_non_text(update: Update) -> None:
    await update.effective_message.reply_text(explain(GuardrailCode.NON_TEXT))
