# tests/integration/test_realtime_paths.py
"""Realtime-critical paths: settings text, corrections, queries, health, split edit state."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.models import UserCategoryCorrection
from app.services.analytics_service import AnalyticsService
from app.services.category_service import CategoryService
from app.services.expense_service import ExpenseService
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import parse_indian_amount


@pytest.mark.asyncio
async def test_health_includes_db_status(api_client):
    resp = await api_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["db_status"] in ("ok", "error")
    assert "version" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_settings_update_profile(db_session, test_user):
    users = UserService(db_session)
    await users.update_profile(test_user, monthly_income=parse_indian_amount("35k"))
    await db_session.refresh(test_user)
    assert test_user.monthly_income == Decimal("35000")


@pytest.mark.asyncio
async def test_category_correction_persists(db_session, test_user):
    await CategoryService(db_session).record_correction(
        test_user.id, "medicine", "food_groceries"
    )
    rows = (
        await db_session.execute(
            select(UserCategoryCorrection).where(
                UserCategoryCorrection.user_id == test_user.id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    block = await CategoryService(db_session).get_user_corrections_for_prompt(test_user.id)
    assert "medicine" in block


@pytest.mark.asyncio
async def test_category_detail_and_top_queries(db_session, test_user):
    await ExpenseService(db_session).create(
        test_user.id,
        amount=Decimal("200"),
        description="petrol",
        category_slug="fuel",
    )
    await ExpenseService(db_session).create(
        test_user.id,
        amount=Decimal("500"),
        description="lunch",
        category_slug="food_outside",
    )
    svc = AnalyticsService(db_session)
    detail = await svc.handle_query(test_user, "category_detail", {"category": "food"})
    assert "₹" in detail or "Food" in detail
    top = await svc.handle_query(test_user, "top_categories", {"n": 2})
    assert "Top" in top


@pytest.mark.asyncio
async def test_split_edit_state_roundtrip(db_session, test_user):
    states = StateService(db_session)
    pending = {
        "type": "split",
        "amount": "600",
        "description": "lunch",
        "split_with": ["Rahul"],
        "split_type": "equal",
    }
    await states.set_state(
        test_user.telegram_user_id,
        "EDIT_SPLIT_WHAT",
        user_id=test_user.id,
        pending_data=pending,
    )
    row = await states.get_state(test_user.telegram_user_id)
    assert row.state == "EDIT_SPLIT_WHAT"
    assert row.pending_data["amount"] == "600"


@pytest.mark.asyncio
async def test_settlement_rejects_empty_person(db_session, test_user):
    from app.core.exceptions import ValidationError
    from app.nlp.schemas import ParsedMessage
    from app.channels.telegram.handlers import debt

    class _Msg:
        async def reply_text(self, *a, **k):
            return None

    class _User:
        id = 1001

    class _Update:
        effective_message = _Msg()
        effective_user = _User()

    parsed = ParsedMessage(type="settlement", settled_person="", confidence=0.9)
    with pytest.raises(ValidationError):
        await debt.show_confirmation(_Update(), test_user.id, parsed)
