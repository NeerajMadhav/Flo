# app/core/database.py
"""Async SQLAlchemy engine, session factory, and atomic transaction helper."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""


def _build_engine():
    settings = get_settings()
    url = settings.database_url
    is_sqlite = url.startswith("sqlite")
    kwargs: dict[str, Any] = {"echo": settings.debug}

    if is_sqlite:
        # WAL allows concurrent readers + one writer — needed for realtime load on SQLite
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        else:
            # NullPool avoids holding stale file locks across async tasks
            kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
        kwargs["pool_pre_ping"] = True  # drop dead connections under load
        kwargs["pool_recycle"] = 1800

    return create_async_engine(url, **kwargs), is_sqlite


engine, _is_sqlite = _build_engine()
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session; always close on exit."""
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()


async def create_all_tables() -> None:
    """Create all tables (dev/tests only — production uses Alembic)."""
    from app.core import models  # noqa: F401
    from sqlalchemy import text

    async with engine.begin() as conn:
        if _is_sqlite:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def atomic(session: AsyncSession):
    """Commit on success; rollback and re-raise on any failure."""
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
