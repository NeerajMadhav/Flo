# tests/conftest.py
"""Shared fixtures — in-memory SQLite, seeded user, ASGI client."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.models import Category, User
from app.core.seed import DEFAULT_CATEGORIES
from app.channels.telegram import middleware as tg_mw
from app.core.concurrency import reset_concurrency_for_tests
from app.utils.idempotency import update_id_cache


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    tg_mw.reset_rate_limits()
    update_id_cache._ids.clear()
    update_id_cache._set.clear()
    reset_concurrency_for_tests()
    yield
    tg_mw.reset_rate_limits()
    reset_concurrency_for_tests()


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        for slug, name, emoji, order in DEFAULT_CATEGORIES:
            session.add(
                Category(
                    slug=slug,
                    display_name=name,
                    icon_emoji=emoji,
                    is_default=True,
                    user_id=None,
                    sort_order=order,
                )
            )
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        telegram_user_id="1001",
        telegram_username="arjun",
        name="Arjun",
        monthly_income=Decimal("30000"),
        monthly_budget=Decimal("20000"),
        onboarded=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    user = User(
        telegram_user_id="2002",
        telegram_username="priya",
        name="Priya",
        onboarded=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, monkeypatch):
    """HTTP client with get_db overridden to use the in-memory session."""
    from app.core.database import get_db
    from app.main import app

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    # Avoid lifespan Telegram/scheduler during tests
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
