# app/services/alert_service.py
"""Budget threshold checks after expense create/update."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.alert_repo import AlertRepository
from app.repositories.expense_repo import ExpenseRepository
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService
from app.utils.currency import format_inr
from app.utils.date_utils import month_start, today_ist


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.alerts = AlertRepository(session)
        self.users = UserRepository(session)
        self.expenses = ExpenseRepository(session)

    async def check_budget(self, user_id: int) -> Optional[str]:
        """Return an alert message if overall monthly budget is crossed, else None."""
        user = await self.users.get_by_id(user_id)
        if not user or not user.is_budget_set:
            return None
        _, total = await self.expenses.count_this_month(user_id, month_start(), today_ist())
        budget = Decimal(user.monthly_budget)
        if total >= budget:
            msg = (
                f"⚠️ Budget alert: you've spent {format_inr(total)} of "
                f"{format_inr(budget)} this month."
            )
            await AuditService(self.session).record(
                "alert.triggered",
                user_id=user_id,
                entity_type="budget",
                new_value={"spent": str(total), "budget": str(budget), "pct": 100},
            )
            await self.session.commit()
            return msg
        if total >= budget * Decimal("0.8"):
            pct = int((total / budget) * 100)
            msg = (
                f"Heads up — {pct}% of your monthly budget used "
                f"({format_inr(total)} / {format_inr(budget)})."
            )
            await AuditService(self.session).record(
                "alert.triggered",
                user_id=user_id,
                entity_type="budget",
                new_value={"spent": str(total), "budget": str(budget), "pct": pct},
            )
            await self.session.commit()
            return msg
        return None
