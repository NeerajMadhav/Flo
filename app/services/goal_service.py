# app/services/goal_service.py
"""Savings goals."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import GoalAlreadyExistsError, GoalNotFoundError, ValidationError
from app.core.models import SavingsGoal
from app.repositories.goal_repo import GoalRepository
from app.services.audit_service import AuditService
from app.utils.currency import format_inr


class GoalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GoalRepository(session)

    async def create(
        self,
        user_id: int,
        name: str,
        target: Decimal,
        target_date: date | None = None,
    ) -> SavingsGoal:
        if target <= 0:
            raise ValidationError("Goal target must be > 0.")
        if await self.repo.get_by_name(user_id, name):
            raise GoalAlreadyExistsError(name)
        goal = SavingsGoal(
            user_id=user_id, name=name, target_amount=target, target_date=target_date
        )
        await self.repo.add(goal)
        await AuditService(self.session).record(
            "goal.created",
            user_id=user_id,
            entity_type="goal",
            entity_id=goal.id,
            new_value={"name": name, "target": str(target)},
        )
        await self.session.commit()
        return goal

    async def contribute(self, user_id: int, name: str, amount: Decimal) -> SavingsGoal:
        goal = await self.repo.get_by_name(user_id, name)
        if not goal:
            raise GoalNotFoundError()
        await self.repo.add_contribution(goal, amount)
        await AuditService(self.session).record(
            "goal.contributed",
            user_id=user_id,
            entity_type="goal",
            entity_id=goal.id,
            new_value={"amount": str(amount), "current": str(goal.current_amount)},
        )
        await self.session.commit()
        return goal

    async def list_goals(self, user_id: int) -> list[SavingsGoal]:
        return await self.repo.list_all(user_id)

    def format_progress(self, goal: SavingsGoal) -> str:
        cur = Decimal(goal.current_amount)
        tgt = Decimal(goal.target_amount)
        pct = int((cur / tgt) * 100) if tgt else 0
        status = "✅ done" if goal.is_completed else f"{pct}%"
        return f"{goal.name}: {format_inr(cur)} / {format_inr(tgt)} ({status})"
