# app/channels/telegram/handlers/fallback.py
"""Unknown / greeting / non-text fallbacks."""

from __future__ import annotations

from telegram import Update


async def handle_unknown(update: Update) -> None:
    await update.effective_message.reply_text(
        "I didn't catch that. Try:\n"
        "• petrol 250\n"
        "• lunch 600 split with Rahul\n"
        "• how much did I spend this month\n"
        "• who owes me"
    )


async def handle_greeting(update: Update, name: str | None = None) -> None:
    who = name or "there"
    await update.effective_message.reply_text(
        f"Hey {who}! 👋 What would you like to log?"
    )


async def handle_non_text(update: Update) -> None:
    await update.effective_message.reply_text(
        "I only read text for now — try typing your expense."
    )
