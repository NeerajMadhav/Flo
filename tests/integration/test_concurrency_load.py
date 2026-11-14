# tests/integration/test_concurrency_load.py
"""Concurrent load: many users + same-user serialization + balance races."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.concurrency import reset_concurrency_for_tests, user_request_lock
from app.core.database import Base
from app.core.models import Category, User
from app.core.seed import DEFAULT_CATEGORIES
from app.repositories.contact_repo import ContactRepository
from app.repositories.expense_repo import ExpenseRepository
from app.services.expense_service import ExpenseService
from app.services.split_service import SplitService
from app.utils.date_utils import month_start, today_ist
from app.utils.idempotency import UpdateIdCache


@pytest.fixture(autouse=True)
def _reset_locks():
    reset_concurrency_for_tests()
    yield
    reset_concurrency_for_tests()


@pytest_asyncio.fixture
async def shared_db():
    """In-memory SQLite shared across concurrent sessions (StaticPool)."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as seed:
        for slug, name, emoji, order in DEFAULT_CATEGORIES:
            seed.add(
                Category(
                    slug=slug,
                    display_name=name,
                    icon_emoji=emoji,
                    is_default=True,
                    user_id=None,
                    sort_order=order,
                )
            )
        await seed.commit()
    yield Session
    await engine.dispose()


@pytest.mark.asyncio
async def test_parallel_expenses_many_users(shared_db):
    """20 users each logging an expense concurrently — all succeed."""
    async with shared_db() as session:
        for i in range(20):
            session.add(
                User(
                    telegram_user_id=f"load-{i}",
                    name=f"User{i}",
                    onboarded=True,
                    is_active=True,
                )
            )
        await session.commit()
        users = list(
            (
                await session.scalars(
                    select(User).where(User.telegram_user_id.like("load-%"))
                )
            ).all()
        )
        assert len(users) == 20
        user_ids = [(u.id, u.telegram_user_id) for u in users]

    async def log_one(user_id: int, tg_id: str):
        async with user_request_lock(tg_id):
            async with shared_db() as session:
                await ExpenseService(session).create(
                    user_id,
                    amount=Decimal("10"),
                    description=f"exp-{tg_id}",
                    category_slug="misc",
                )

    await asyncio.gather(*(log_one(uid, tg) for uid, tg in user_ids))

    async with shared_db() as session:
        total_count = 0
        for uid, _ in user_ids:
            rows = await ExpenseRepository(session).list_for_period(
                uid, month_start(), today_ist()
            )
            total_count += len(rows)
        assert total_count == 20


@pytest.mark.asyncio
async def test_same_user_lock_serializes():
    """Two overlapping requests for one user run one-after-another."""
    order: list[str] = []

    async def work(label: str):
        async with user_request_lock("same-user"):
            order.append(f"{label}-start")
            await asyncio.sleep(0.05)
            order.append(f"{label}-end")

    await asyncio.gather(work("a"), work("b"))
    assert order in (
        ["a-start", "a-end", "b-start", "b-end"],
        ["b-start", "b-end", "a-start", "a-end"],
    )


@pytest.mark.asyncio
async def test_concurrent_balance_adjustments(shared_db):
    """10 parallel +50 adjustments → net_balance == 500."""
    async with shared_db() as session:
        user = User(
            telegram_user_id="bal-user",
            name="Bal",
            onboarded=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        contact = await ContactRepository(session).get_or_create(user.id, "RaceFriend")
        await session.commit()
        user_id = user.id
        contact_id = contact.id

    async def bump():
        async with user_request_lock(f"bal-{user_id}"):
            async with shared_db() as session:
                from app.core.models import Contact

                c = await session.get(Contact, contact_id)
                await ContactRepository(session).adjust_balance(c, Decimal("50"))
                await session.commit()

    await asyncio.gather(*(bump() for _ in range(10)))

    async with shared_db() as session:
        from app.core.models import Contact

        fresh = await session.get(Contact, contact_id)
        assert Decimal(fresh.net_balance) == Decimal("500")


@pytest.mark.asyncio
async def test_update_id_check_and_mark_atomic():
    cache = UpdateIdCache(maxlen=100)

    async def once(uid: int) -> bool:
        return await cache.check_and_mark(uid)

    results = await asyncio.gather(*(once(42) for _ in range(20)))
    assert results.count(False) == 1
    assert results.count(True) == 19


@pytest.mark.asyncio
async def test_parallel_splits_different_contacts(shared_db):
    """Multiple splits for one user serialized — each contact balance 100."""
    async with shared_db() as session:
        user = User(telegram_user_id="split-user", name="S", onboarded=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id
        tg_id = user.telegram_user_id

    names = [f"Friend{i}" for i in range(5)]

    async def one_split(name: str):
        async with user_request_lock(tg_id):
            async with shared_db() as session:
                await SplitService(session).create_split_expense(
                    user_id,
                    amount=Decimal("200"),
                    description=f"with {name}",
                    category_slug="misc",
                    expense_date=today_ist(),
                    split_type="equal",
                    split_with=[name],
                )

    await asyncio.gather(*(one_split(n) for n in names))

    async with shared_db() as session:
        contacts = ContactRepository(session)
        for n in names:
            c = await contacts.get_by_name(user_id, n)
            assert c is not None
            assert Decimal(c.net_balance) == Decimal("100.00")
