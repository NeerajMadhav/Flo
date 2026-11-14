# tests/integration/test_alerts_and_onboarding.py
"""Budget alerts + user onboarding completion."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.models import User
from app.services.alert_service import AlertService
from app.services.expense_service import ExpenseService
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_onboarding_complete(db_session):
    users = UserService(db_session)
    user, is_new = await users.get_or_create("5555", "newbie")
    assert is_new is True
    assert user.onboarded is False
    done = await users.complete_onboarding(
        user,
        name="Sam",
        monthly_income=Decimal("25000"),
        monthly_budget=Decimal("15000"),
    )
    assert done.onboarded is True
    assert done.name == "Sam"


@pytest.mark.asyncio
async def test_budget_alert_at_80_percent(db_session, test_user):
    # budget 20000 → 80% = 16000
    await ExpenseService(db_session).create(
        test_user.id,
        amount=Decimal("16000"),
        description="Big",
        category_slug="rent",
    )
    msg = await AlertService(db_session).check_budget(test_user.id)
    assert msg is not None
    assert "80" in msg or "Budget" in msg or "Heads up" in msg


@pytest.mark.asyncio
async def test_no_alert_when_under_threshold(db_session, test_user):
    await ExpenseService(db_session).create(
        test_user.id,
        amount=Decimal("100"),
        description="Small",
        category_slug="misc",
    )
    msg = await AlertService(db_session).check_budget(test_user.id)
    assert msg is None


@pytest.mark.asyncio
async def test_set_active_blocked(db_session, test_user):
    users = UserService(db_session)
    await users.set_active(test_user.telegram_user_id, False)
    await db_session.refresh(test_user)
    assert test_user.is_active is False
