# app/channels/telegram/handlers/queries.py
"""Query-intent routing — act on ledger, then speak naturally."""

from __future__ import annotations

from telegram import Update

from app.channels.telegram.handlers import debt as debt_handler
from app.channels.telegram.memory import remember_bot_reply
from app.channels.telegram.presence import show_typing
from app.core.database import AsyncSessionLocal
from app.nlp.schemas import ParsedMessage
from app.services.analytics_service import AnalyticsService
from app.services.goal_service import GoalService
from app.services.nlp_service import NLPService
from app.services.recurring_service import RecurringService
from app.services.user_service import UserService


async def _speak_facts(
    update: Update, user_id: int, facts: str, *, situation: str
) -> None:
    """Deterministic FACTS in → natural assistant reply out."""
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    await show_typing(update)
    async with AsyncSessionLocal() as session:
        reply = await NLPService(session).compose_reply(
            user_id,
            tg_id,
            user_message=msg.text or "",
            facts=facts,
            situation=situation,
            fallback=facts,
        )
    await msg.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


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
                await _speak_facts(
                    update,
                    user_id,
                    "No goals yet. Suggest: save 50000 for new phone",
                    situation="goal_progress_empty",
                )
                return
            svc = GoalService(session)
            text = "\n".join(svc.format_progress(g) for g in goals)
        await _speak_facts(update, user_id, text, situation="goal_progress")
        return
    if intent == "recurring_list":
        async with AsyncSessionLocal() as session:
            rows = await RecurringService(session).list_active(user_id)
            if not rows:
                await _speak_facts(
                    update,
                    user_id,
                    "No recurring expenses yet.",
                    situation="recurring_empty",
                )
                return
            svc = RecurringService(session)
            text = "\n".join(svc.format_line(r) for r in rows)
        await _speak_facts(update, user_id, text, situation="recurring_list")
        return

    async with AsyncSessionLocal() as session:
        user = await UserService(session).users.get_by_id(user_id)
        text = await AnalyticsService(session).handle_query(user, intent, params)
    await _speak_facts(update, user_id, text, situation=f"query:{intent or 'general'}")
