# app/channels/telegram/handlers/fallback.py
"""Unknown / greeting / non-text — fast templates (no second LLM call)."""

from __future__ import annotations

from telegram import Update

from app.channels.telegram.replies import send as reply_send
from app.utils.guardrails import GuardrailCode, bot_name, explain


async def handle_unknown(update: Update, user_id: int | None = None) -> None:
    """Steer back to money tracking without a slow second model call."""
    del user_id  # reserved for future personalization
    reply = (
        f"Hmm, I didn't catch a clear expense yet 🤔\n"
        f"Send one bill at a time, e.g. electricity 1200 or fuel 578 split with Surya."
    )
    await reply_send(update, reply)


async def handle_greeting(update: Update, user_id: int, name: str | None = None) -> None:
    del user_id
    who = name or "there"
    if who.strip().lower() in ("hi", "hey", "hello", "ok", "okay"):
        who = "there"
    reply = (
        f"Hey {who}! I'm {bot_name()} 👋\n"
        f"Log a spend, split a bill, or ask what you've spent — what's up?"
    )
    await reply_send(update, reply)


async def handle_non_text(update: Update) -> None:
    await reply_send(update, explain(GuardrailCode.NON_TEXT))
