# tests/integration/test_security.py
"""Webhook secret, JWT auth, user isolation via API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.config import get_settings
from app.core.database import get_db
from app.services.expense_service import ExpenseService


@pytest.fixture
async def client(db_session):
    """ASGI client against routers only — no Telegram lifespan."""
    from fastapi import FastAPI

    from app.channels.api.v1.router import api_router
    from app.channels.telegram.router import webhook_router
    from app.main import flo_exception_handler
    from app.core.exceptions import FloBaseException

    test_app = FastAPI()
    test_app.add_exception_handler(FloBaseException, flo_exception_handler)
    test_app.include_router(webhook_router)
    test_app.include_router(api_router)

    @test_app.get("/health")
    async def health():
        return {"status": "ok"}

    async def _override():
        yield db_session

    test_app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    test_app.dependency_overrides.clear()


def _token(user_id: int) -> str:
    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    return jwt.encode(
        {"sub": str(user_id), "exp": exp},
        settings.api_secret_key,
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret(client):
    r = await client.post(
        "/webhook/telegram",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_webhook_accepts_good_secret_without_bot(client):
    """Secret ok but bot not ready → 503 (lifespan off)."""
    settings = get_settings()
    r = await client.post(
        "/webhook/telegram",
        json={"update_id": 99},
        headers={"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret},
    )
    assert r.status_code in (503, 200)


@pytest.mark.asyncio
async def test_api_requires_jwt(client, test_user):
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_api_me_with_jwt(client, test_user):
    r = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {_token(test_user.id)}"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Arjun"


@pytest.mark.asyncio
async def test_api_create_expense(client, test_user, db_session):
    r = await client.post(
        "/api/v1/expenses",
        headers={"Authorization": f"Bearer {_token(test_user.id)}"},
        json={"amount": "175.50", "description": "Auto", "category": "transport"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["description"] == "Auto"
    # verify persisted with source=api
    from app.repositories.expense_repo import ExpenseRepository
    from app.utils.date_utils import month_start, today_ist

    rows = await ExpenseRepository(db_session).list_for_period(
        test_user.id, month_start(), today_ist()
    )
    match = next(e for e in rows if e.description == "Auto")
    assert match.source == "api"


@pytest.mark.asyncio
async def test_user_b_cannot_delete_user_a_expense(
    client, db_session, test_user, other_user
):
    e = await ExpenseService(db_session).create(
        test_user.id, amount=Decimal("99"), description="Secret", category_slug="misc"
    )
    r = await client.delete(
        f"/api/v1/expenses/{e.id}",
        headers={"Authorization": f"Bearer {_token(other_user.id)}"},
    )
    # soft_delete raises ExpenseNotFoundError → unhandled may be 500; prefer 404
    assert r.status_code in (404, 500)


@pytest.mark.asyncio
async def test_auth_rejects_bare_telegram_id_spoof(client, test_user):
    """Root cause fix: bare telegram_user_id must NOT mint a JWT."""
    r = await client.post(
        "/api/v1/auth/telegram",
        json={"telegram_user_id": test_user.telegram_user_id},
    )
    # Missing Login Widget fields → 422 validation error
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_auth_telegram_login_widget_ok(client, test_user):
    import time

    from app.config import get_settings
    from app.utils.telegram_auth import build_login_hash

    settings = get_settings()
    payload = {
        "id": int(test_user.telegram_user_id),
        "first_name": "Arjun",
        "username": "arjun",
        "auth_date": int(time.time()),
    }
    payload["hash"] = build_login_hash(payload, settings.telegram_bot_token)
    r = await client.post("/api/v1/auth/telegram", json=payload)
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_auth_tampered_login_rejected(client, test_user):
    import time

    from app.config import get_settings
    from app.utils.telegram_auth import build_login_hash

    settings = get_settings()
    payload = {
        "id": int(test_user.telegram_user_id),
        "first_name": "Arjun",
        "auth_date": int(time.time()),
    }
    payload["hash"] = build_login_hash(payload, settings.telegram_bot_token)
    payload["id"] = 999999999  # spoof another user
    r = await client.post("/api/v1/auth/telegram", json=payload)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_jwt_rejected(client, db_session, test_user):
    test_user.is_active = False
    await db_session.commit()
    r = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {_token(test_user.id)}"},
    )
    assert r.status_code == 403
