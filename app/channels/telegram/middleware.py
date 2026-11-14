# app/channels/telegram/middleware.py
"""Telegram rate limiting helpers — async-safe under concurrent load."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from time import monotonic

from app.config import get_settings
from app.core.exceptions import RateLimitExceededError

_windows: dict[str, deque[float]] = defaultdict(deque)
_lock = asyncio.Lock()


def reset_rate_limits() -> None:
    """Clear all in-memory rate-limit windows (tests / admin)."""
    _windows.clear()


async def check_rate_limit(telegram_user_id: str) -> None:
    """Raise RateLimitExceededError if user exceeds messages/min or burst."""
    settings = get_settings()
    now = monotonic()
    async with _lock:
        q = _windows[telegram_user_id]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.rate_limit_messages_per_min:
            raise RateLimitExceededError()
        burst = sum(1 for t in q if now - t <= 5)
        if burst >= settings.rate_limit_burst_per_5s:
            raise RateLimitExceededError()
        q.append(now)


# Sync wrapper kept for unit tests that call without await
def check_rate_limit_sync(telegram_user_id: str) -> None:
    """Synchronous rate-limit check (unit tests only)."""
    settings = get_settings()
    now = monotonic()
    q = _windows[telegram_user_id]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_messages_per_min:
        raise RateLimitExceededError()
    burst = sum(1 for t in q if now - t <= 5)
    if burst >= settings.rate_limit_burst_per_5s:
        raise RateLimitExceededError()
    q.append(now)
