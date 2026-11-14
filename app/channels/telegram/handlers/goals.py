# app/channels/telegram/handlers/goals.py
"""Goal create / contribute from parsed NLP."""

from __future__ import annotations

from decimal import Decimal

from telegram import Update

from app.core.database import AsyncSessionLocal
from app.nlp.schemas import ParsedMessage
from app.services.goal_service import GoalService


async def handle(update: Update, user_id: int, parsed: ParsedMessage) -> None:
    msg = update.effective_message
    action = parsed.goal_action or "set"
    async with AsyncSessionLocal() as session:
        svc = GoalService(session)
        if action == "set" and parsed.goal_name and parsed.goal_amount:
            goal = await svc.create(user_id, parsed.goal_name, Decimal(parsed.goal_amount))
            await msg.reply_text(f"Goal set ✅ {svc.format_progress(goal)}")
            return
        if action == "deposit" and parsed.goal_name and parsed.goal_amount:
            goal = await svc.contribute(
                user_id, parsed.goal_name, Decimal(parsed.goal_amount)
            )
            await msg.reply_text(f"Added ✅ {svc.format_progress(goal)}")
            return
        if action == "check":
            goals = await svc.list_goals(user_id)
            if not goals:
                await msg.reply_text("No goals yet.")
                return
            await msg.reply_text("\n".join(svc.format_progress(g) for g in goals))
            return
    await msg.reply_text("Try: save 50000 for new phone")


async def handle_state(update: Update, state) -> None:
    """GOAL_* states — guide user back to one-shot NLP goal phrasing."""
    await update.effective_message.reply_text(
        "Tell me the goal in one line, e.g. save 50000 for new phone"
    )
