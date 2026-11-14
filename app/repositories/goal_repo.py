# app/repositories/goal_repo.py
"""Savings goal persistence."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import SavingsGoal
from app.repositories.base import BaseRepository


class GoalRepository(BaseRepository[SavingsGoal]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SavingsGoal)

    async def list_active(self, user_id: int) -> list[SavingsGoal]:
        result = await self.session.scalars(
            select(SavingsGoal).where(
                SavingsGoal.user_id == user_id, SavingsGoal.is_completed.is_(False)
            )
        )
        return list(result.all())

    async def list_all(self, user_id: int) -> list[SavingsGoal]:
        result = await self.session.scalars(
            select(SavingsGoal).where(SavingsGoal.user_id == user_id)
        )
        return list(result.all())

    async def get_by_name(self, user_id: int, name: str) -> Optional[SavingsGoal]:
        return await self.session.scalar(
            select(SavingsGoal).where(
                SavingsGoal.user_id == user_id, SavingsGoal.name == name
            )
        )

    async def add_contribution(self, goal: SavingsGoal, amount: Decimal) -> SavingsGoal:
        goal.current_amount = Decimal(goal.current_amount) + amount
        if goal.current_amount >= goal.target_amount:
            goal.is_completed = True
        await self.session.flush()
        return goal
