# app/channels/telegram/handlers/goals.py
"""Goal create / contribute from parsed NLP."""

from __future__ import annotations

from decimal import Decimal

from telegram import Update

from app.channels.telegram.memory import remember_bot_reply
from app.core.database import AsyncSessionLocal
from app.nlp.schemas import ParsedMessage
from app.services.goal_service import GoalService


async def handle(update: Update, user_id: int, parsed: ParsedMessage) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    action = parsed.goal_action or "set"
    async with AsyncSessionLocal() as session:
        svc = GoalService(session)
        if action == "set" and parsed.goal_name and parsed.goal_amount:
            goal = await svc.create(user_id, parsed.goal_name, Decimal(parsed.goal_amount))
            reply = f"Goal set ✅ {svc.format_progress(goal)}"
            await msg.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return
        if action == "deposit" and parsed.goal_name and parsed.goal_amount:
            goal = await svc.contribute(
                user_id, parsed.goal_name, Decimal(parsed.goal_amount)
            )
            reply = f"Added ✅ {svc.format_progress(goal)}"
            await msg.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return
        if action == "check":
            goals = await svc.list_goals(user_id)
            if not goals:
                reply = "No goals yet."
                await msg.reply_text(reply)
                await remember_bot_reply(tg_id, reply)
                return
            reply = "\n".join(svc.format_progress(g) for g in goals)
            await msg.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return
    reply = "Try: save 50000 for new phone"
    await msg.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def handle_state(update: Update, state) -> None:
    """GOAL_* states — guide user back to one-shot NLP goal phrasing."""
    tg_id = str(update.effective_user.id)
    reply = "Tell me the goal in one line, e.g. save 50000 for new phone"
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)
