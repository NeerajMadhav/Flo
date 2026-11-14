# app/services/user_service.py
"""User onboarding, profile, and NLP context."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UserNotFoundError, UserNotOnboardedError
from app.core.models import User
from app.repositories.expense_repo import ExpenseRepository
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService
from app.utils.currency import format_inr
from app.utils.date_utils import format_display, month_end, month_start, today_ist
from app.utils.sanitizer import sanitize_display_name, sanitize_for_prompt


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.expenses = ExpenseRepository(session)

    async def get_or_create(
        self, telegram_user_id: str, telegram_username: str | None = None
    ) -> tuple[User, bool]:
        """Return (user, is_new). Safe under concurrent /start races."""
        from sqlalchemy.exc import IntegrityError

        user = await self.users.get_by_telegram_id(telegram_user_id)
        if user:
            return user, False
        try:
            user = await self.users.create(telegram_user_id, telegram_username)
            await AuditService(self.session).record(
                "user.created",
                user_id=user.id,
                entity_type="user",
                entity_id=user.id,
                source="telegram",
            )
            await self.session.commit()
            return user, True
        except IntegrityError:
            # Two parallel first messages — unique telegram_user_id collision
            await self.session.rollback()
            user = await self.users.get_by_telegram_id(telegram_user_id)
            if not user:
                raise
            return user, False

    async def get_profile(self, telegram_user_id: str) -> User:
        user = await self.users.get_by_telegram_id(telegram_user_id)
        if not user:
            raise UserNotFoundError()
        if not user.onboarded:
            raise UserNotOnboardedError()
        return user

    async def complete_onboarding(
        self,
        user: User,
        *,
        name: str,
        age: int | None = None,
        monthly_income: Decimal | None = None,
        monthly_budget: Decimal | None = None,
    ) -> User:
        clean_name = sanitize_display_name(name)
        if len(clean_name) < 2:
            from app.core.exceptions import ValidationError

            raise ValidationError("Name must be at least 2 characters.")
        user.name = clean_name
        user.age = age
        user.monthly_income = monthly_income
        user.monthly_budget = monthly_budget
        user.onboarded = True
        await self.users.save(user)
        await AuditService(self.session).record(
            "user.onboarded",
            user_id=user.id,
            entity_type="user",
            entity_id=user.id,
            source="telegram",
            name=user.name,
        )
        await self.session.commit()
        return user

    async def update_profile(self, user: User, **fields: object) -> User:
        if "name" in fields and fields["name"] is not None:
            fields["name"] = sanitize_display_name(str(fields["name"]))
            if len(str(fields["name"])) < 2:
                from app.core.exceptions import ValidationError

                raise ValidationError("Name must be at least 2 characters.")
        for k, v in fields.items():
            if hasattr(user, k) and v is not None:
                setattr(user, k, v)
        await self.users.save(user)
        await self.session.commit()
        return user

    async def get_prompt_context(self, user_id: int) -> str:
        """Build {user_context_block} for NLP prompts (sanitized)."""
        user = await self.users.get_by_id(user_id)
        if not user:
            return "Unknown user"
        income = format_inr(user.monthly_income) + "/month" if user.is_income_set else "No income set"
        budget = format_inr(user.monthly_budget) + "/month" if user.is_budget_set else "No budget set"
        last = await self.expenses.last_expense(user_id)
        safe_name = sanitize_for_prompt(user.name or "Friend", max_len=64)
        if last:
            days = (today_ist() - last.date).days
            desc = sanitize_for_prompt(last.description or "Expense", max_len=80)
            last_line = (
                f"Last logged: {desc} "
                f"{format_inr(last.amount)} on {format_display(last.date)} ({days} days ago)"
            )
        else:
            last_line = "First message — no prior expenses logged."
        return f"User: {safe_name} | Income: {income} | Budget: {budget}\n{last_line}"

    async def get_welcome_back_summary(self, user_id: int) -> str:
        user = await self.users.get_by_id(user_id)
        if not user:
            return "Welcome back! 👋"
        start, end = month_start(), month_end()
        count, total = await self.expenses.count_this_month(user_id, start, end)
        raw = (user.name or "").strip()
        greetish = {"hi", "hey", "hello", "ok", "okay", "yes", "no", "friend"}
        name = "there" if not raw or raw.lower() in greetish else raw
        if count == 0:
            return f"Welcome back, {name}! 👋\nNo expenses logged this month yet."
        return (
            f"Welcome back, {name}! 👋\n"
            f"This month: {count} expenses · {format_inr(total)}"
        )

    async def set_active(self, telegram_user_id: str, active: bool) -> None:
        user = await self.users.get_by_telegram_id(telegram_user_id)
        if user:
            user.is_active = active
            await self.session.commit()
