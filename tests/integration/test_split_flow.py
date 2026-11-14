# tests/integration/test_split_flow.py
"""Split create → participants + contact net_balance (both directions)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.repositories.contact_repo import ContactRepository
from app.repositories.split_repo import SplitRepository
from app.services.split_service import SplitService
from app.utils.date_utils import today_ist


@pytest.mark.asyncio
async def test_equal_split_they_owe_me(db_session, test_user):
    svc = SplitService(db_session)
    expense = await svc.create_split_expense(
        test_user.id,
        amount=Decimal("900"),
        description="Dinner",
        category_slug="food_outside",
        expense_date=today_ist(),
        split_type="equal",
        split_with=["Ravi", "Priya"],
    )
    assert expense.is_split is True
    parts = await SplitRepository(db_session).list_for_expense(expense.id)
    assert len(parts) == 2
    assert all(p.direction == "they_owe_me" for p in parts)
    ravi = await ContactRepository(db_session).get_by_name(test_user.id, "Ravi")
    assert ravi is not None
    assert Decimal(ravi.net_balance) > 0


@pytest.mark.asyncio
async def test_they_paid_negative_balance(db_session, test_user):
    svc = SplitService(db_session)
    await svc.create_split_expense(
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
    surya = await ContactRepository(db_session).get_by_name(test_user.id, "Surya")
    assert surya is not None
    assert Decimal(surya.net_balance) < 0  # I owe Surya


@pytest.mark.asyncio
async def test_percent_split_persists(db_session, test_user):
    svc = SplitService(db_session)
    expense = await svc.create_split_expense(
        test_user.id,
        amount=Decimal("900"),
        description="Electricity",
        category_slug="utilities",
        expense_date=today_ist(),
        split_type="percent",
        split_with=["Surya", "Karthik"],
        split_amounts={"me": 40, "Surya": 30, "Karthik": 30},
    )
    parts = await SplitRepository(db_session).list_for_expense(expense.id)
    assert {p.person_name for p in parts} == {"Surya", "Karthik"}
    assert all(p.user_share == Decimal("360.00") for p in parts)
