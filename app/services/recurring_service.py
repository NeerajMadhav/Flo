# app/services/recurring_service.py
"""Recurring expense reminders."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import RecurringExpense
from app.repositories.recurring_repo import RecurringRepository
from app.services.category_service import CategoryService
from app.utils.currency import format_inr
from app.utils.date_utils import clamp_due_day, today_ist


class RecurringService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = RecurringRepository(session)
        self.categories = CategoryService(session)

    async def create(
        self,
        user_id: int,
        *,
        description: str,
        amount: Decimal,
        category_slug: str | None,
        frequency: str = "monthly",
        due_day: int | None = None,
    ) -> RecurringExpense:
        cat = await self.categories.resolve(category_slug, user_id)
        row = RecurringExpense(
            user_id=user_id,
            description=description,
            amount=amount,
            category_id=cat.id,
            frequency=frequency,
            due_day=due_day or today_ist().day,
        )
        await self.repo.add(row)
        await self.session.commit()
        return row

    async def list_active(self, user_id: int) -> list[RecurringExpense]:
        return await self.repo.list_active(user_id)

    def format_line(self, row: RecurringExpense) -> str:
        day = f" on day {row.due_day}" if row.due_day else ""
        return f"{row.description} {format_inr(row.amount)} ({row.frequency}{day})"

    async def due_soon(self) -> list[tuple[RecurringExpense, object]]:
        """Return recurring rows whose due date is within remind_days_before."""
        today = today_ist()
        rows = await self.repo.list_all_active()
        out = []
        for r in rows:
            if r.frequency != "monthly" or not r.due_day:
                continue
            due = clamp_due_day(today.year, today.month, r.due_day)
            days_left = (due - today).days
            if 0 <= days_left <= (r.remind_days_before or 2):
                out.append((r, due))
        return out
