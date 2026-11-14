# app/core/concurrency.py
"""Per-user locks and global NLP concurrency limiter for realtime load."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.config import get_settings

# One lock per telegram_user_id — serializes a single user's messages so
# state machine transitions never interleave (confirm vs new expense race).
_user_locks: dict[str, asyncio.Lock] = {}
_user_locks_guard = asyncio.Lock()

# Cap parallel OpenRouter calls across all users (protect free-tier / upstream).
_nlp_semaphore: asyncio.Semaphore | None = None


async def _get_user_lock(telegram_user_id: str) -> asyncio.Lock:
    async with _user_locks_guard:
        lock = _user_locks.get(telegram_user_id)
        if lock is None:
            lock = asyncio.Lock()
            _user_locks[telegram_user_id] = lock
        return lock


@asynccontextmanager
async def user_request_lock(telegram_user_id: str) -> AsyncIterator[None]:
    """Hold while processing one Telegram/API mutation for this user."""
    lock = await _get_user_lock(telegram_user_id)
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()


def get_nlp_semaphore() -> asyncio.Semaphore:
    """Lazy singleton semaphore sized from settings."""
    global _nlp_semaphore
    if _nlp_semaphore is None:
        limit = max(1, int(getattr(get_settings(), "nlp_max_concurrent", 8)))
        _nlp_semaphore = asyncio.Semaphore(limit)
    return _nlp_semaphore


@asynccontextmanager
async def nlp_slot() -> AsyncIterator[None]:
    """Acquire a slot before calling OpenRouter."""
    sem = get_nlp_semaphore()
    await sem.acquire()
    try:
        yield
    finally:
        sem.release()


def reset_concurrency_for_tests() -> None:
    """Clear locks/semaphore between tests."""
    global _nlp_semaphore
    _user_locks.clear()
    _nlp_semaphore = None
