# app/repositories/split_repo.py
"""Split participant persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import SplitParticipant


class SplitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_many(self, rows: list[SplitParticipant]) -> list[SplitParticipant]:
        for r in rows:
            self.session.add(r)
        await self.session.flush()
        return rows

    async def list_for_expense(self, expense_id: int) -> list[SplitParticipant]:
        result = await self.session.scalars(
            select(SplitParticipant).where(SplitParticipant.expense_id == expense_id)
        )
        return list(result.all())

    async def unsettled_for_person(
        self, expense_ids: list[int], person_name: str
    ) -> list[SplitParticipant]:
        if not expense_ids:
            return []
        result = await self.session.scalars(
            select(SplitParticipant).where(
                SplitParticipant.expense_id.in_(expense_ids),
                SplitParticipant.person_name == person_name,
                SplitParticipant.is_settled.is_(False),
            )
        )
        return list(result.all())

    async def mark_settled(self, row: SplitParticipant) -> SplitParticipant:
        row.is_settled = True
        row.settled_at = datetime.now(timezone.utc)
        await self.session.flush()
        return row
