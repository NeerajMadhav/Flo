# app/repositories/expense_repo.py
"""Expense persistence with soft-delete support."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.models import Expense, SplitParticipant
from app.repositories.base import BaseRepository


class ExpenseRepository(BaseRepository[Expense]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Expense)

    async def create(self, expense: Expense) -> Expense:
        return await self.add(expense)

    async def get_with_participants(self, expense_id: int, user_id: int) -> Optional[Expense]:
        stmt = (
            select(Expense)
            .options(selectinload(Expense.participants), selectinload(Expense.category))
            .where(Expense.id == expense_id, Expense.user_id == user_id)
        )
        return await self.session.scalar(stmt)

    async def list_for_period(
        self,
        user_id: int,
        start: date,
        end: date,
        *,
        include_deleted: bool = False,
    ) -> list[Expense]:
        cond = [
            Expense.user_id == user_id,
            Expense.date >= start,
            Expense.date <= end,
        ]
        if not include_deleted:
            cond.append(Expense.is_deleted.is_(False))
        stmt = (
            select(Expense)
            .options(selectinload(Expense.category), selectinload(Expense.participants))
            .where(and_(*cond))
            .order_by(Expense.date.desc(), Expense.id.desc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def soft_delete(self, expense: Expense) -> Expense:
        expense.is_deleted = True
        expense.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return expense

    async def restore(self, expense: Expense) -> Expense:
        expense.is_deleted = False
        expense.deleted_at = None
        await self.session.flush()
        return expense

    async def last_expense(self, user_id: int) -> Optional[Expense]:
        stmt = (
            select(Expense)
            .where(Expense.user_id == user_id, Expense.is_deleted.is_(False))
            .order_by(Expense.date.desc(), Expense.id.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def sum_user_spend(self, user_id: int, start: date, end: date) -> Decimal:
        """Sum actual user cost: non-split amount + split user_share for 'me' direction."""
        expenses = await self.list_for_period(user_id, start, end)
        total = Decimal("0")
        for e in expenses:
            if not e.is_split:
                total += Decimal(e.amount)
            else:
                # user_share is stored on each participant row as the user's cost for that split
                # For analytics: use first participant's user_share (same for all rows of one expense)
                if e.participants:
                    total += Decimal(e.participants[0].user_share)
                else:
                    total += Decimal(e.amount)
        return total

    async def search(
        self, user_id: int, query: str, limit: int = 10
    ) -> list[Expense]:
        stmt = (
            select(Expense)
            .where(
                Expense.user_id == user_id,
                Expense.is_deleted.is_(False),
                Expense.description.ilike(f"%{query}%"),
            )
            .order_by(Expense.date.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_this_month(self, user_id: int, start: date, end: date) -> tuple[int, Decimal]:
        expenses = await self.list_for_period(user_id, start, end)
        total = Decimal("0")
        for e in expenses:
            if e.is_split and e.participants:
                total += Decimal(e.participants[0].user_share)
            else:
                total += Decimal(e.amount)
        return len(expenses), total
