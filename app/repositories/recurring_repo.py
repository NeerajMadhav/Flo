# app/repositories/recurring_repo.py
"""Recurring expense persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import RecurringExpense
from app.repositories.base import BaseRepository


class RecurringRepository(BaseRepository[RecurringExpense]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RecurringExpense)

    async def list_active(self, user_id: int) -> list[RecurringExpense]:
        result = await self.session.scalars(
            select(RecurringExpense).where(
                RecurringExpense.user_id == user_id, RecurringExpense.is_active.is_(True)
            )
        )
        return list(result.all())

    async def list_all_active(self) -> list[RecurringExpense]:
        result = await self.session.scalars(
            select(RecurringExpense).where(RecurringExpense.is_active.is_(True))
        )
        return list(result.all())
