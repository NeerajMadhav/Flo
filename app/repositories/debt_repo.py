# app/repositories/debt_repo.py
"""Debt queries spanning expenses + split_participants."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.models import Expense, SplitParticipant


class DebtRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def unsettled_splits(self, user_id: int) -> list[SplitParticipant]:
        stmt = (
            select(SplitParticipant)
            .join(Expense)
            .options(selectinload(SplitParticipant.expense))
            .where(
                Expense.user_id == user_id,
                Expense.is_deleted.is_(False),
                SplitParticipant.is_settled.is_(False),
            )
        )
        return list((await self.session.scalars(stmt)).all())

    async def unsettled_for_contact(
        self, user_id: int, person_name: str
    ) -> list[SplitParticipant]:
        stmt = (
            select(SplitParticipant)
            .join(Expense)
            .where(
                Expense.user_id == user_id,
                Expense.is_deleted.is_(False),
                SplitParticipant.person_name == person_name,
                SplitParticipant.is_settled.is_(False),
            )
            .order_by(SplitParticipant.id)
        )
        return list((await self.session.scalars(stmt)).all())
