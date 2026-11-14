# app/channels/telegram/handlers/queries.py
"""Query-intent routing (spend summaries, debts, goals)."""

from __future__ import annotations

from telegram import Update

from app.channels.telegram.handlers import debt as debt_handler
from app.core.database import AsyncSessionLocal
from app.nlp.schemas import ParsedMessage
from app.services.analytics_service import AnalyticsService
from app.services.goal_service import GoalService
from app.services.recurring_service import RecurringService
from app.services.user_service import UserService


async def handle(update: Update, user_id: int, parsed: ParsedMessage) -> None:
    msg = update.effective_message
    intent = parsed.query_intent or ""
    params = parsed.query_params or {}

    if intent == "who_owes_me":
        await debt_handler.show_who_owes_me(update, user_id)
        return
    if intent in ("i_owe_who", "net_balance_contact"):
        await debt_handler.show_i_owe(update, user_id, params.get("contact"))
        return
    if intent == "goal_progress":
        async with AsyncSessionLocal() as session:
            goals = await GoalService(session).list_goals(user_id)
            if not goals:
                await msg.reply_text("No goals yet. Try: save 50000 for new phone")
                return
            svc = GoalService(session)
            text = "\n".join(svc.format_progress(g) for g in goals)
        await msg.reply_text(text)
        return
    if intent == "recurring_list":
        async with AsyncSessionLocal() as session:
            rows = await RecurringService(session).list_active(user_id)
            if not rows:
                await msg.reply_text("No recurring expenses yet.")
                return
            svc = RecurringService(session)
            text = "\n".join(svc.format_line(r) for r in rows)
        await msg.reply_text(text)
        return

    async with AsyncSessionLocal() as session:
        user = await UserService(session).users.get_by_id(user_id)
        text = await AnalyticsService(session).handle_query(user, intent, params)
    await msg.reply_text(text)
