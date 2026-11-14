# tests/integration/test_debt_flow.py
"""Settlements — partial, full, bidirectional net balance."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.repositories.contact_repo import ContactRepository
from app.services.debt_service import DebtService
from app.services.split_service import SplitService
from app.utils.date_utils import today_ist


@pytest.mark.asyncio
async def test_partial_settlement_they_pay(db_session, test_user):
    split = SplitService(db_session)
    await split.create_split_expense(
        test_user.id,
        amount=Decimal("600"),
        description="Cab",
        category_slug="transport",
        expense_date=today_ist(),
        split_type="equal",
        split_with=["Rahul"],
    )
    contact = await ContactRepository(db_session).get_by_name(test_user.id, "Rahul")
    owed_before = Decimal(contact.net_balance)
    assert owed_before == Decimal("300.00")

    debts = DebtService(db_session)
    updated = await debts.settle(test_user.id, "Rahul", Decimal("100"), "they_pay")
    assert Decimal(updated.net_balance) == Decimal("200.00")


@pytest.mark.asyncio
async def test_full_settlement_zeros_balance(db_session, test_user):
    await SplitService(db_session).create_split_expense(
        test_user.id,
        amount=Decimal("400"),
        description="Movie",
        category_slug="entertainment",
        expense_date=today_ist(),
        split_type="equal",
        split_with=["Neha"],
    )
    debts = DebtService(db_session)
    updated = await debts.settle(test_user.id, "Neha", None, "they_pay")
    assert Decimal(updated.net_balance) == Decimal("0")


@pytest.mark.asyncio
async def test_i_pay_settlement_after_they_paid_split(db_session, test_user):
    await SplitService(db_session).create_split_expense(
        test_user.id,
        amount=Decimal("500"),
        description="Groceries",
        category_slug="food_groceries",
        expense_date=today_ist(),
        split_type="equal",
        split_with=["Amit"],
        split_total_people=2,
        split_payer="Amit",
    )
    contact = await ContactRepository(db_session).get_by_name(test_user.id, "Amit")
    assert Decimal(contact.net_balance) == Decimal("-250.00")

    updated = await DebtService(db_session).settle(
        test_user.id, "Amit", Decimal("250"), "i_pay"
    )
    assert Decimal(updated.net_balance) == Decimal("0")


@pytest.mark.asyncio
async def test_who_owes_me_and_i_owe_lists(db_session, test_user):
    svc = SplitService(db_session)
    await svc.create_split_expense(
        test_user.id,
        amount=Decimal("200"),
        description="A",
        category_slug="misc",
        expense_date=today_ist(),
        split_type="equal",
        split_with=["CreditorFriend"],
    )
    await svc.create_split_expense(
        test_user.id,
        amount=Decimal("200"),
        description="B",
        category_slug="misc",
        expense_date=today_ist(),
        split_type="equal",
        split_with=["DebtorFriend"],
        split_total_people=2,
        split_payer="DebtorFriend",
    )
    debts = DebtService(db_session)
    owe_me = await debts.who_owes_me(test_user.id)
    i_owe = await debts.i_owe_who(test_user.id)
    assert any(c.canonical_name == "CreditorFriend" for c in owe_me)
    assert any(c.canonical_name == "DebtorFriend" for c in i_owe)
