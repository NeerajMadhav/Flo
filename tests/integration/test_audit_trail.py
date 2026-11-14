# tests/integration/test_audit_trail.py
"""Durable audit_log + request_id middleware end-to-end."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.models import AuditLog
from app.services.audit_service import AuditService
from app.services.expense_service import ExpenseService
from app.services.goal_service import GoalService
from app.services.user_service import UserService
from app.utils.logger import request_id_var


@pytest.mark.asyncio
async def test_expense_create_writes_audit_row(db_session, test_user):
    token = request_id_var.set("audit-exp-1")
    try:
        exp = await ExpenseService(db_session).create(
            test_user.id,
            amount=Decimal("250"),
            description="petrol",
            category_slug="fuel",
            source="telegram",
        )
        rows = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "expense.created",
                    AuditLog.entity_id == exp.id,
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].user_id == test_user.id
        assert rows[0].new_value is not None
        assert rows[0].new_value.get("request_id") == "audit-exp-1"
    finally:
        request_id_var.reset(token)


@pytest.mark.asyncio
async def test_user_onboard_and_goal_audit(db_session):
    users = UserService(db_session)
    user, created = await users.get_or_create("9001", "newbie")
    assert created is True
    created_rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "user.created", AuditLog.user_id == user.id)
        )
    ).scalars().all()
    assert len(created_rows) == 1

    await users.complete_onboarding(
        user,
        name="Sam",
        age=28,
        monthly_income=Decimal("40000"),
        monthly_budget=Decimal("15000"),
    )
    onboard_rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user.onboarded", AuditLog.user_id == user.id
            )
        )
    ).scalars().all()
    assert len(onboard_rows) == 1

    goal = await GoalService(db_session).create(user.id, "phone", Decimal("50000"))
    goal_rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "goal.created", AuditLog.entity_id == goal.id)
        )
    ).scalars().all()
    assert len(goal_rows) == 1


@pytest.mark.asyncio
async def test_auth_login_failed_audited(api_client, db_session, test_user):
    resp = await api_client.post(
        "/api/v1/auth/telegram",
        json={
            "id": int(test_user.telegram_user_id),
            "first_name": "Arjun",
            "auth_date": 1_700_000_000,
            "hash": "deadbeef",
        },
        headers={"X-Request-ID": "auth-fail-1"},
    )
    assert resp.status_code == 401
    assert resp.headers.get("X-Request-ID") == "auth-fail-1"
    rows = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "auth.login_failed"))
    ).scalars().all()
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_health_echoes_request_id(api_client):
    resp = await api_client.get("/health", headers={"X-Request-ID": "health-rid-9"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == "health-rid-9"


@pytest.mark.asyncio
async def test_audit_service_skips_non_durable_events(db_session, test_user):
    await AuditService(db_session).record(
        "nlp.parse.success",
        user_id=test_user.id,
        source="nlp",
    )
    await db_session.commit()
    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "nlp.parse.success")
        )
    ).scalars().all()
    assert rows == []
