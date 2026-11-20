# app/channels/telegram/handlers/queries.py
"""Query-intent routing — act on ledger, reply fast (no second LLM)."""

from __future__ import annotations

from decimal import Decimal

from telegram import Update

from app.channels.telegram.formatters import category_emoji
from app.channels.telegram.handlers import debt as debt_handler
from app.channels.telegram.presence import show_typing
from app.channels.telegram.replies import send as reply_send
from app.core.database import AsyncSessionLocal
from app.nlp.schemas import ParsedMessage
from app.services.analytics_service import AnalyticsService
from app.services.category_service import CategoryService
from app.services.expense_service import ExpenseService
from app.services.goal_service import GoalService
from app.services.recurring_service import RecurringService
from app.services.user_service import UserService
from app.utils.currency import format_inr
from app.utils.date_utils import month_end, month_start


async def _reply(update: Update, text: str) -> None:
    await reply_send(update, text)


async def _progress(update: Update, detail: str) -> None:
    """Short ACK for multi-step ledger work."""
    await show_typing(update)
    await reply_send(
        update,
        f"⏳ Gathering the relevant info for your ask…\n{detail}",
    )


def _format_expense_line(e) -> str:
    slug = e.category.slug if getattr(e, "category", None) else "misc"
    emo = (e.category.icon_emoji if getattr(e, "category", None) else None) or category_emoji(
        slug
    )
    amt = format_inr(e.amount)
    desc = e.description or "Expense"
    return f"{emo} {desc} — {amt} · {e.date}"


async def handle(update: Update, user_id: int, parsed: ParsedMessage) -> None:
    intent = parsed.query_intent or ""
    params = parsed.query_params or {}

    if intent == "who_owes_me":
        await debt_handler.show_who_owes_me(update, user_id)
        return
    if intent in ("i_owe_who", "net_balance_contact"):
        await debt_handler.show_i_owe(update, user_id, params.get("contact"))
        return
    if intent in ("category_breakdown_month", "category_breakdown_week"):
        await _progress(update, "Breaking down spend by category")
        async with AsyncSessionLocal() as session:
            user = await UserService(session).users.get_by_id(user_id)
            text = await AnalyticsService(session).handle_query(user, intent, params)
        await _reply(update, text)
        return

    if intent in ("list_categories", "help_categories", "categories"):
        async with AsyncSessionLocal() as session:
            cats = await CategoryService(session).list_display(user_id)
        if not cats:
            await _reply(update, "No categories yet — I'll sort as you log.")
            return
        lines = [
            f"{c.icon_emoji or category_emoji(c.slug)} {c.display_name}"
            for c in cats[:24]
        ]
        await _reply(
            update,
            "Categories I know:\n"
            + "\n".join(lines)
            + "\n\nJust say what it was — I'll pick one 🙂",
        )
        return

    if intent == "count_expenses":
        async with AsyncSessionLocal() as session:
            rows = await ExpenseService(session).repo.list_for_period(
                user_id, month_start(), month_end()
            )
        total_amt = sum((e.amount for e in rows), Decimal("0"))
        n = len(rows)
        await _reply(
            update,
            f"📊 This month: {n} expense{'s' if n != 1 else ''} · {format_inr(total_amt)}\n"
            f"Say list expenses to see them, or fuel expenses to filter.",
        )
        return

    if intent == "list_expenses":
        cat_filter = (params.get("category") or "").strip().lower()
        if cat_filter:
            await _progress(update, f"Filtering {cat_filter} expenses")
        async with AsyncSessionLocal() as session:
            rows = await ExpenseService(session).repo.list_for_period(
                user_id, month_start(), month_end()
            )
        if cat_filter:
            rows = [
                e
                for e in rows
                if (e.category and e.category.slug == cat_filter)
                or (
                    e.category
                    and cat_filter in (e.category.display_name or "").lower()
                )
                or cat_filter in (e.description or "").lower()
            ]
        if not rows:
            label = f" for {cat_filter}" if cat_filter else ""
            await _reply(
                update,
                f"No expenses{label} this month yet. Log one like: petrol 250 ⛽",
            )
            return
        rows = sorted(rows, key=lambda e: (e.date, e.id), reverse=True)
        lines = [_format_expense_line(e) for e in rows[:15]]
        extra = f"\n…and {len(rows) - 15} more" if len(rows) > 15 else ""
        title = (
            f"📋 {cat_filter} this month ({len(rows)})"
            if cat_filter
            else f"📋 This month ({len(rows)})"
        )
        await _reply(
            update,
            f"{title}:\n"
            + "\n".join(lines)
            + extra
            + "\n\nTip: fuel expenses · list expenses · delete last expense",
        )
        return

    if intent == "manage_expenses":
        async with AsyncSessionLocal() as session:
            last = await ExpenseService(session).repo.last_expense(user_id)
        tip = ""
        if last:
            tip = f"\n\nLatest: {_format_expense_line(last)}"
        await _reply(
            update,
            "Yes — you can manage logged spends:\n"
            "• list expenses — see this month\n"
            "• delete last expense — remove the newest one\n"
            "• Or correct category: that medicine was groceries"
            + tip,
        )
        return

    if intent == "delete_last_expense":
        async with AsyncSessionLocal() as session:
            svc = ExpenseService(session)
            last = await svc.repo.last_expense(user_id)
            if not last:
                await _reply(update, "Nothing to delete — no expenses logged yet.")
                return
            line = _format_expense_line(last)
            await svc.soft_delete(user_id, last.id)
        await _reply(update, f"🗑️ Removed:\n{line}\n\n(Say list expenses to see what's left.)")
        return

    if intent == "goal_progress":
        async with AsyncSessionLocal() as session:
            goals = await GoalService(session).list_goals(user_id)
            if not goals:
                await _reply(update, "No goals yet. Try: save 50000 for new phone 🎯")
                return
            svc = GoalService(session)
            text = "🎯 Goals:\n" + "\n".join(svc.format_progress(g) for g in goals)
        await _reply(update, text)
        return
    if intent == "recurring_list":
        async with AsyncSessionLocal() as session:
            rows = await RecurringService(session).list_active(user_id)
            if not rows:
                await _reply(update, "No recurring expenses yet.")
                return
            svc = RecurringService(session)
            text = "🔁 Recurring:\n" + "\n".join(svc.format_line(r) for r in rows)
        await _reply(update, text)
        return
    if intent == "help":
        await _reply(
            update,
            "I can:\n"
            "• Log: petrol 250 ⛽\n"
            "• Split: fuel 578 split with Surya\n"
            "• List: list expenses · how many expenses\n"
            "• Filter: fuel expenses · food expenses\n"
            "• Break down: by category\n"
            "• Fix: delete last expense\n"
            "• Ask: how much this month · who owes me",
        )
        return

    async with AsyncSessionLocal() as session:
        user = await UserService(session).users.get_by_id(user_id)
        text = await AnalyticsService(session).handle_query(user, intent, params)
    await _reply(update, text)
