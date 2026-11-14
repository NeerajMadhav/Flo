# app/channels/telegram/handlers/fallback.py
"""Unknown / greeting / non-text — conversational assistant voice."""

from __future__ import annotations

from telegram import Update

from app.channels.telegram.memory import remember_bot_reply
from app.channels.telegram.presence import show_typing
from app.core.database import AsyncSessionLocal
from app.services.nlp_service import NLPService
from app.utils.guardrails import GuardrailCode, bot_name, explain


async def handle_unknown(update: Update, user_id: int | None = None) -> None:
    """Natural redirect when intent is unclear — not a canned menu dump."""
    tg_id = str(update.effective_user.id)
    user_text = update.effective_message.text or ""
    canned = explain(GuardrailCode.UNKNOWN)
    await show_typing(update)
    if user_id is None:
        await update.effective_message.reply_text(canned)
        await remember_bot_reply(tg_id, canned)
        return
    async with AsyncSessionLocal() as session:
        reply = await NLPService(session).compose_reply(
            user_id,
            tg_id,
            user_message=user_text,
            facts=(
                "Intent unclear. Flo tracks expenses, splits, settlements, "
                "budgets, goals, and spend queries. Ask the user naturally "
                "what they want to log or check — do not invent a transaction."
            ),
            situation="unknown_intent",
            fallback=canned,
        )
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def handle_greeting(update: Update, user_id: int, name: str | None = None) -> None:
    """Warm assistant hello that invites the next need."""
    tg_id = str(update.effective_user.id)
    who = name or "there"
    canned = f"Hey {who}! I'm {bot_name()} 👋 What would you like to log or check?"
    await show_typing(update)
    async with AsyncSessionLocal() as session:
        reply = await NLPService(session).compose_reply(
            user_id,
            tg_id,
            user_message=update.effective_message.text or "hi",
            facts=(
                f"User's display name: {who}. Bot name: {bot_name()}. "
                "Greet briefly and ask what money thing they need "
                "(log spend, split, debt, budget, goals)."
            ),
            situation="greeting",
            fallback=canned,
        )
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def handle_non_text(update: Update) -> None:
    tg_id = str(update.effective_user.id)
    reply = explain(GuardrailCode.NON_TEXT)
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)
