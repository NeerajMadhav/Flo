# app/services/analytics_service.py
"""Spending queries — always uses user_share for splits."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BudgetNotSetError
from app.core.models import User
from app.repositories.expense_repo import ExpenseRepository
from app.repositories.user_repo import UserRepository
from app.utils.currency import format_inr
from app.utils.date_utils import month_end, month_start, today_ist, week_start


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.expenses = ExpenseRepository(session)
        self.users = UserRepository(session)

    def _user_cost(self, expense) -> Decimal:
        if expense.is_split and expense.participants:
            return Decimal(expense.participants[0].user_share)
        return Decimal(expense.amount)

    async def total(self, user_id: int, start: date, end: date) -> Decimal:
        rows = await self.expenses.list_for_period(user_id, start, end)
        return sum((self._user_cost(e) for e in rows), Decimal("0"))

    async def category_breakdown(
        self, user_id: int, start: date, end: date
    ) -> list[tuple[str, Decimal]]:
        rows = await self.expenses.list_for_period(user_id, start, end)
        buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for e in rows:
            name = e.category.display_name if e.category else "Misc"
            buckets[name] += self._user_cost(e)
        return sorted(buckets.items(), key=lambda x: x[1], reverse=True)

    async def remaining_budget(self, user: User) -> tuple[Decimal, Decimal, Decimal]:
        if not user.is_budget_set:
            raise BudgetNotSetError()
        spent = await self.total(user.id, month_start(), today_ist())
        budget = Decimal(user.monthly_budget)
        return budget, spent, budget - spent

    async def handle_query(self, user: User, intent: str, params: dict) -> str:
        """Map query_intent → human reply text."""
        today = today_ist()
        if intent == "total_spent_today":
            t = await self.total(user.id, today, today)
            return f"Today you've spent {format_inr(t)}."
        if intent == "total_spent_week":
            t = await self.total(user.id, week_start(), today)
            return f"This week you've spent {format_inr(t)}."
        if intent == "total_spent_month":
            t = await self.total(user.id, month_start(), today)
            return f"This month you've spent {format_inr(t)}."
        if intent in ("category_breakdown_month", "category_breakdown_week"):
            start = month_start() if "month" in intent else week_start()
            rows = await self.category_breakdown(user.id, start, today)
            if not rows:
                return "No expenses in this period yet."
            lines = [f"• {name}: {format_inr(amt)}" for name, amt in rows[:10]]
            return "Breakdown:\n" + "\n".join(lines)
        if intent == "remaining_budget":
            budget, spent, left = await self.remaining_budget(user)
            return (
                f"Budget {format_inr(budget)} · Spent {format_inr(spent)} · "
                f"Left {format_inr(left)}"
            )
        if intent == "last_expense":
            last = await self.expenses.last_expense(user.id)
            if not last:
                return "No expenses logged yet."
            share = self._user_cost(last)
            return f"Last: {last.description} {format_inr(share)} on {last.date}"
        if intent == "category_detail":
            cat = str(params.get("category") or params.get("query") or "").strip()
            if not cat:
                return "Which category? e.g. how much on food this month"
            rows = await self.category_breakdown(user.id, month_start(), today)
            match = [(n, a) for n, a in rows if cat.lower() in n.lower()]
            if not match:
                return f"No spending matched '{cat}' this month."
            lines = [f"• {name}: {format_inr(amt)}" for name, amt in match]
            total = sum((a for _, a in match), Decimal("0"))
            return f"{cat.title()} this month: {format_inr(total)}\n" + "\n".join(lines)
        if intent in ("top_categories", "top_n_categories"):
            n = int(params.get("n") or params.get("limit") or 3)
            rows = await self.category_breakdown(user.id, month_start(), today)
            if not rows:
                return "No expenses this month yet."
            lines = [f"• {name}: {format_inr(amt)}" for name, amt in rows[: max(1, n)]]
            return f"Top {min(n, len(rows))} categories this month:\n" + "\n".join(lines)
        if intent == "expense_search":
            q = str(params.get("query") or params.get("brand") or "")
            found = await self.expenses.search(user.id, q)
            if not found:
                return f"No expenses matching '{q}'."
            lines = [
                f"• {e.description} {format_inr(self._user_cost(e))} ({e.date})"
                for e in found[:8]
            ]
            return "\n".join(lines)
        if intent == "last_n_days":
            n = int(params.get("n") or 7)
            start = today - timedelta(days=n - 1)
            t = await self.total(user.id, start, today)
            return f"Last {n} days: {format_inr(t)}"
        if intent == "help":
            return (
                "Try:\n• petrol 250\n• lunch 600 split with Rahul\n"
                "• how much did I spend this month\n• who owes me"
            )
        return "I can look that up — try 'this month' or 'who owes me'."
