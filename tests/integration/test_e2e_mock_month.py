# tests/integration/test_e2e_mock_month.py
"""Realtime-style mock month: expenses + splits + settle + analytics as a whole."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.analytics_service import AnalyticsService
from app.services.debt_service import DebtService
from app.services.expense_service import ExpenseService
from app.services.split_service import SplitService
from app.utils.date_utils import month_start, today_ist


@pytest.mark.asyncio
async def test_full_month_mock_scenario(db_session, test_user):
    """
    Mock data for Arjun's month:
      - petrol 250 (personal)
      - groceries 900 split equal with Ravi+Priya  → user share 300
      - Surya paid lunch 480 / 2                   → user owes 240
      - Ravi pays back 200 of his 300 debt
    Assert final analytics + balances.
    """
    expenses = ExpenseService(db_session)
    splits = SplitService(db_session)
    debts = DebtService(db_session)
    analytics = AnalyticsService(db_session)

    await expenses.create(
        test_user.id, amount=Decimal("250"), description="Petrol", category_slug="fuel"
    )
    await splits.create_split_expense(
        test_user.id,
        amount=Decimal("900"),
        description="Groceries",
        category_slug="food_groceries",
        expense_date=today_ist(),
        split_type="equal",
        split_with=["Ravi", "Priya"],
    )
    await splits.create_split_expense(
        test_user.id,
        amount=Decimal("480"),
        description="Lunch",
        category_slug="food_outside",
        expense_date=today_ist(),
        split_type="equal",
        split_with=["Surya"],
        split_total_people=2,
        split_payer="Surya",
    )
    await debts.settle(test_user.id, "Ravi", Decimal("200"), "they_pay")

    # Spend = 250 + 300 + 240 = 790 (user_share for both splits)
    total = await analytics.total(test_user.id, month_start(), today_ist())
    assert total == Decimal("790.00")

    owe_me = await debts.who_owes_me(test_user.id)
    i_owe = await debts.i_owe_who(test_user.id)

    ravi = next(c for c in owe_me if c.canonical_name == "Ravi")
    assert Decimal(ravi.net_balance) == Decimal("100.00")  # 300 - 200
    priya = next(c for c in owe_me if c.canonical_name == "Priya")
    assert Decimal(priya.net_balance) == Decimal("300.00")
    surya = next(c for c in i_owe if c.canonical_name == "Surya")
    assert Decimal(surya.net_balance) == Decimal("-240.00")

    budget, spent, left = await analytics.remaining_budget(test_user)
    assert spent == Decimal("790.00")
    assert left == Decimal("19210.00")
