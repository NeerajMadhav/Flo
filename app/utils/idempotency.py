# app/utils/idempotency.py
"""In-memory update_id deduplication for Telegram webhook retries."""

from __future__ import annotations

import asyncio
from collections import deque


class UpdateIdCache:
    """Keep the last N processed Telegram update_ids (async-safe)."""

    def __init__(self, maxlen: int = 1000) -> None:
        self._ids: deque[int] = deque(maxlen=maxlen)
        self._set: set[int] = set()
        self._lock = asyncio.Lock()

    def seen(self, update_id: int) -> bool:
        return update_id in self._set

    def mark(self, update_id: int) -> None:
        if update_id in self._set:
            return
        if len(self._ids) == self._ids.maxlen and self._ids:
            old = self._ids[0]
            self._set.discard(old)
        self._ids.append(update_id)
        self._set.add(update_id)

    async def check_and_mark(self, update_id: int) -> bool:
        """
        Atomically: return True if already seen; else mark and return False.
        Use this on the webhook hot path under concurrent delivery.
        """
        async with self._lock:
            if update_id in self._set:
                return True
            self.mark(update_id)
            return False


update_id_cache = UpdateIdCache()
