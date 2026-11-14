# app/repositories/alert_repo.py
"""Budget alert persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import BudgetAlert
from app.repositories.base import BaseRepository


class AlertRepository(BaseRepository[BudgetAlert]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BudgetAlert)

    async def list_active(self, user_id: int) -> list[BudgetAlert]:
        result = await self.session.scalars(
            select(BudgetAlert).where(
                BudgetAlert.user_id == user_id, BudgetAlert.is_active.is_(True)
            )
        )
        return list(result.all())
