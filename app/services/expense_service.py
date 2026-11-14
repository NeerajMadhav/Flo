# app/services/expense_service.py
"""Personal expense create / update / soft-delete / restore."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import ExpenseNotFoundError, RestoreWindowExpiredError, ValidationError
from app.core.models import Expense
from app.repositories.expense_repo import ExpenseRepository
from app.services.alert_service import AlertService
from app.services.audit_service import AuditService
from app.services.category_service import CategoryService
from app.utils.date_utils import today_ist


class ExpenseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ExpenseRepository(session)
        self.categories = CategoryService(session)

    async def create(
        self,
        user_id: int,
        *,
        amount: Decimal,
        description: str | None = None,
        category_slug: str | None = None,
        expense_date: date | None = None,
        quantity: Decimal | None = None,
        unit: str | None = None,
        upi_ref: str | None = None,
        raw_message: str | None = None,
        source: str = "telegram",
    ) -> Expense:
        settings = get_settings()
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0.")
        if amount > Decimal(str(settings.max_amount_per_transaction)):
            raise ValidationError("Amount exceeds the maximum allowed.")
        cat = await self.categories.resolve(category_slug, user_id)
        expense = Expense(
            user_id=user_id,
            amount=amount,
            category_id=cat.id,
            description=description,
            date=expense_date or today_ist(),
            quantity=quantity,
            unit=unit,
            upi_ref=upi_ref,
            raw_message=raw_message,
            source=source,
            is_split=False,
        )
        await self.repo.create(expense)
        await AuditService(self.session).record(
            "expense.created",
            user_id=user_id,
            entity_type="expense",
            entity_id=expense.id,
            source=source,
            amount=str(amount),
            category=category_slug,
            is_split=False,
        )
        await self.session.commit()
        # Budget alert after create
        await AlertService(self.session).check_budget(user_id)
        return expense

    async def get(self, user_id: int, expense_id: int) -> Expense:
        e = await self.repo.get_with_participants(expense_id, user_id)
        if not e:
            raise ExpenseNotFoundError()
        return e

    async def soft_delete(self, user_id: int, expense_id: int) -> Expense:
        e = await self.get(user_id, expense_id)
        await self.repo.soft_delete(e)
        await AuditService(self.session).record(
            "expense.deleted",
            user_id=user_id,
            entity_type="expense",
            entity_id=e.id,
            old_value={"amount": str(e.amount), "description": e.description},
        )
        await self.session.commit()
        return e

    async def restore(self, user_id: int, expense_id: int) -> Expense:
        e = await self.get(user_id, expense_id)
        if not e.is_deleted or not e.deleted_at:
            raise ExpenseNotFoundError()
        deleted_at = e.deleted_at
        if deleted_at.tzinfo is None:
            deleted_at = deleted_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - deleted_at > timedelta(days=7):
            raise RestoreWindowExpiredError()
        await self.repo.restore(e)
        await AuditService(self.session).record(
            "expense.restored",
            user_id=user_id,
            entity_type="expense",
            entity_id=e.id,
        )
        await self.session.commit()
        return e
