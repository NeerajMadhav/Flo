# tests/integration/test_analytics.py
"""Analytics uses user_share for splits; budget NULL raises."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.exceptions import BudgetNotSetError
from app.core.models import User
from app.services.analytics_service import AnalyticsService
from app.services.expense_service import ExpenseService
from app.services.split_service import SplitService
from app.utils.date_utils import month_start, today_ist


@pytest.mark.asyncio
async def test_month_total_personal(db_session, test_user):
    await ExpenseService(db_session).create(
        test_user.id, amount=Decimal("250"), description="Petrol", category_slug="fuel"
    )
    total = await AnalyticsService(db_session).total(
        test_user.id, month_start(), today_ist()
    )
    assert total == Decimal("250")


@pytest.mark.asyncio
async def test_month_total_uses_user_share_not_bill(db_session, test_user):
    """Split ₹900 equal 3-way → user cost ₹300, not ₹900."""
    await SplitService(db_session).create_split_expense(
        test_user.id,
        amount=Decimal("900"),
        description="Dinner",
        category_slug="food_outside",
        expense_date=today_ist(),
        split_type="equal",
        split_with=["Ravi", "Priya"],
    )
    total = await AnalyticsService(db_session).total(
        test_user.id, month_start(), today_ist()
    )
    assert total == Decimal("300.00")


@pytest.mark.asyncio
async def test_category_breakdown(db_session, test_user):
    await ExpenseService(db_session).create(
        test_user.id, amount=Decimal("100"), description="A", category_slug="fuel"
    )
    await ExpenseService(db_session).create(
        test_user.id, amount=Decimal("200"), description="B", category_slug="fuel"
    )
    rows = await AnalyticsService(db_session).category_breakdown(
        test_user.id, month_start(), today_ist()
    )
    assert rows[0][1] == Decimal("300")


@pytest.mark.asyncio
async def test_remaining_budget(db_session, test_user):
    await ExpenseService(db_session).create(
        test_user.id, amount=Decimal("5000"), description="Rent-ish", category_slug="rent"
    )
    budget, spent, left = await AnalyticsService(db_session).remaining_budget(test_user)
    assert budget == Decimal("20000")
    assert spent == Decimal("5000")
    assert left == Decimal("15000")


@pytest.mark.asyncio
async def test_budget_not_set_raises(db_session):
    user = User(
        telegram_user_id="9999",
        name="NoBudget",
        onboarded=True,
        monthly_budget=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    with pytest.raises(BudgetNotSetError):
        await AnalyticsService(db_session).remaining_budget(user)


@pytest.mark.asyncio
async def test_query_intents_text(db_session, test_user):
    await ExpenseService(db_session).create(
        test_user.id, amount=Decimal("80"), description="Chai", category_slug="food_outside"
    )
    svc = AnalyticsService(db_session)
    today = await svc.handle_query(test_user, "total_spent_today", {})
    assert "₹" in today or "80" in today
    help_text = await svc.handle_query(test_user, "help", {})
    assert "petrol" in help_text.lower() or "spend" in help_text.lower()
