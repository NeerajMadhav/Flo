# tests/integration/test_expense_flow.py
"""Personal expense create / soft-delete / restore / validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.exceptions import RestoreWindowExpiredError, ValidationError
from app.services.expense_service import ExpenseService


@pytest.mark.asyncio
async def test_create_personal_expense(db_session, test_user):
    svc = ExpenseService(db_session)
    e = await svc.create(
        test_user.id,
        amount=Decimal("250"),
        description="Petrol",
        category_slug="fuel",
        source="telegram",
    )
    assert e.id
    assert e.amount == Decimal("250")
    assert e.source == "telegram"
    assert e.is_deleted is False


@pytest.mark.asyncio
async def test_reject_zero_and_over_max(db_session, test_user):
    svc = ExpenseService(db_session)
    with pytest.raises(ValidationError):
        await svc.create(test_user.id, amount=Decimal("0"), description="bad")
    with pytest.raises(ValidationError):
        await svc.create(test_user.id, amount=Decimal("9999999"), description="too big")


@pytest.mark.asyncio
async def test_soft_delete_and_restore_within_window(db_session, test_user):
    svc = ExpenseService(db_session)
    e = await svc.create(
        test_user.id, amount=Decimal("100"), description="Chai", category_slug="food_outside"
    )
    deleted = await svc.soft_delete(test_user.id, e.id)
    assert deleted.is_deleted is True
    restored = await svc.restore(test_user.id, e.id)
    assert restored.is_deleted is False


@pytest.mark.asyncio
async def test_restore_after_7_days_fails(db_session, test_user):
    svc = ExpenseService(db_session)
    e = await svc.create(
        test_user.id, amount=Decimal("100"), description="Old", category_slug="misc"
    )
    await svc.soft_delete(test_user.id, e.id)
    e.deleted_at = datetime.now(timezone.utc) - timedelta(days=8)
    await db_session.commit()
    with pytest.raises(RestoreWindowExpiredError):
        await svc.restore(test_user.id, e.id)


@pytest.mark.asyncio
async def test_user_isolation_cannot_read_other(db_session, test_user, other_user):
    svc = ExpenseService(db_session)
    e = await svc.create(
        test_user.id, amount=Decimal("50"), description="Mine", category_slug="misc"
    )
    with pytest.raises(Exception):
        await svc.get(other_user.id, e.id)
