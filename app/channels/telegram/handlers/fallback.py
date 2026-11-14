# app/channels/telegram/handlers/fallback.py
"""Unknown / greeting / non-text — fast templates (no second LLM call)."""

from __future__ import annotations

from telegram import Update

from app.channels.telegram.memory import remember_bot_reply
from app.utils.guardrails import GuardrailCode, bot_name, explain


async def handle_unknown(update: Update, user_id: int | None = None) -> None:
    """Steer back to money tracking without a slow second model call."""
    del user_id  # reserved for future personalization
    tg_id = str(update.effective_user.id)
    reply = (
        f"Hmm, I didn't catch a clear expense yet 🤔\n"
        f"Send one bill at a time, e.g. electricity 1200 or fuel 578 split with Surya."
    )
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def handle_greeting(update: Update, user_id: int, name: str | None = None) -> None:
    del user_id
    tg_id = str(update.effective_user.id)
    who = name or "there"
    if who.strip().lower() in ("hi", "hey", "hello", "ok", "okay"):
        who = "there"
    reply = (
        f"Hey {who}! I'm {bot_name()} 👋\n"
        f"Log a spend, split a bill, or ask what you've spent — what's up?"
    )
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def handle_non_text(update: Update) -> None:
    tg_id = str(update.effective_user.id)
    reply = explain(GuardrailCode.NON_TEXT)
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)
