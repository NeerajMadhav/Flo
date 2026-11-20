# app/core/turn_manager.py
"""
Per-user turn coordination: debounce merge, queue, and cancel/supersede.

Bursts of Telegram messages:
- clear intents process immediately
- short fragments within DEBOUNCE → merge into one text
- fragment while a turn is busy → merge onto active text and re-run (halt prior reply)
- explicit cancel / "actually…" → supersede in-flight turn
- independent full intents → queue (finish first, then second)
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

from app.nlp.fast_intent import try_fast_intent
from app.nlp.heuristics import try_heuristic_parse

DEBOUNCE_SEC = 0.45

_SUPERSEDE = re.compile(
    r"^(?:never\s*mind|nvm|stop|cancel that|ignore(\s+that)?|forget(\s+it)?|"
    r"wait|no\s+wait|actually\b)",
    re.IGNORECASE,
)


@dataclass
class TurnTicket:
    """One processable user turn (may be merged text)."""

    tg_id: str
    gen: int
    text: str
    created_at: float = field(default_factory=time.monotonic)

    def alive(self, manager: "TurnManager") -> bool:
        return manager.is_alive(self.tg_id, self.gen)


class TurnManager:
    """In-memory coordinator — one process / one bot instance."""

    def __init__(self) -> None:
        self._gen: dict[str, int] = {}
        self._active_gen: dict[str, int] = {}
        self._active_text: dict[str, str] = {}
        self._buf: dict[str, list[str]] = {}
        self._buf_deadline: dict[str, float] = {}
        self._queue: dict[str, list[str]] = {}
        self._busy: dict[str, bool] = {}
        self._lock = asyncio.Lock()

    def _bump(self, tg_id: str) -> int:
        n = self._gen.get(tg_id, 0) + 1
        self._gen[tg_id] = n
        self._active_gen[tg_id] = n
        return n

    def is_alive(self, tg_id: str, gen: int) -> bool:
        return self._active_gen.get(tg_id) == gen

    @staticmethod
    def _clear_intent(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if try_fast_intent(t) is not None:
            return True
        if try_heuristic_parse(t) is not None:
            return True
        if re.search(r"\d", t) and len(t.split()) >= 2:
            return True
        return False

    @staticmethod
    def _looks_fragment(text: str) -> bool:
        t = (text or "").strip()
        if not t or len(t) <= 3:
            return True
        if re.match(
            r"^(with|and|for|to|from|also|plus|of|on|₹|rs\.?)\b",
            t,
            re.I,
        ):
            return True
        if TurnManager._clear_intent(t):
            return False
        return len(t.split()) <= 4 and not t.endswith("?")

    @staticmethod
    def _should_supersede(new_text: str) -> bool:
        """Only explicit cancel / redirect — not every new clear intent."""
        return bool(_SUPERSEDE.search((new_text or "").strip()))

    def _start_ticket(self, tg_id: str, text: str) -> TurnTicket:
        gen = self._bump(tg_id)
        self._busy[tg_id] = True
        self._active_text[tg_id] = text
        return TurnTicket(tg_id=tg_id, gen=gen, text=text)

    async def collect(self, tg_id: str, text: str) -> TurnTicket | None:
        """
        Buffer/merge/queue incoming text.
        Returns a ticket when this caller should process; None if absorbed.
        """
        text = (text or "").strip()
        if not text:
            return None

        async with self._lock:
            if self._busy.get(tg_id):
                if self._should_supersede(text):
                    # User cancelled / redirected — halt prior reply, run this next
                    self._bump(tg_id)
                    self._queue[tg_id] = [text]
                    self._active_text[tg_id] = text
                elif self._looks_fragment(text) and not self._clear_intent(text):
                    # Two-part message: merge onto in-flight text and re-run
                    prev = (self._active_text.get(tg_id) or "").strip()
                    merged = f"{prev} {text}".strip() if prev else text
                    self._bump(tg_id)
                    self._queue[tg_id] = [merged]
                    self._active_text[tg_id] = merged
                else:
                    # Independent ask — finish current, then this
                    self._queue.setdefault(tg_id, []).append(text)
                return None

            # Immediate path for clear intents (no debounce delay)
            if self._clear_intent(text) and not self._buf.get(tg_id):
                return self._start_ticket(tg_id, text)

            buf = self._buf.setdefault(tg_id, [])
            buf.append(text)
            self._buf_deadline[tg_id] = time.monotonic() + DEBOUNCE_SEC

        await asyncio.sleep(DEBOUNCE_SEC)

        async with self._lock:
            if self._busy.get(tg_id):
                leftover = self._buf.pop(tg_id, [])
                self._buf_deadline.pop(tg_id, None)
                if leftover:
                    self._queue.setdefault(tg_id, []).extend(leftover)
                return None

            deadline = self._buf_deadline.get(tg_id, 0)
            extra = max(0.0, deadline - time.monotonic())

        if extra > 0:
            await asyncio.sleep(extra)

        async with self._lock:
            if self._busy.get(tg_id):
                leftover = self._buf.pop(tg_id, [])
                self._buf_deadline.pop(tg_id, None)
                if leftover:
                    self._queue.setdefault(tg_id, []).extend(leftover)
                return None

            parts = self._buf.pop(tg_id, [])
            self._buf_deadline.pop(tg_id, None)
            if not parts:
                return None

            merged, spill = self._merge_parts(parts)
            if spill:
                self._queue.setdefault(tg_id, []).extend(spill)
            return self._start_ticket(tg_id, merged)

    def _merge_parts(self, parts: list[str]) -> tuple[str, list[str]]:
        if len(parts) == 1:
            return parts[0], []
        if all(self._looks_fragment(p) for p in parts[1:]):
            return " ".join(parts), []
        # Multiple full intents: first now, rest queued
        clear_idx = [
            i
            for i, p in enumerate(parts)
            if self._clear_intent(p) or not self._looks_fragment(p)
        ]
        if len(clear_idx) >= 2:
            first_i = clear_idx[0]
            head = " ".join(parts[: first_i + 1])
            spill = parts[first_i + 1 :]
            return head, spill
        return " ".join(parts), []

    async def finish(self, ticket: TurnTicket) -> str | None:
        """Mark turn done; return next queued text if any."""
        async with self._lock:
            # Always clear busy so queued / superseded work can run
            self._busy[ticket.tg_id] = False
            if self._active_gen.get(ticket.tg_id) == ticket.gen:
                self._active_text.pop(ticket.tg_id, None)
            q = self._queue.get(ticket.tg_id) or []
            if not q:
                return None
            nxt = q.pop(0)
            self._queue[ticket.tg_id] = q
            return nxt

    async def begin_queued(self, tg_id: str, text: str) -> TurnTicket:
        async with self._lock:
            return self._start_ticket(tg_id, text)


_manager: TurnManager | None = None


def get_turn_manager() -> TurnManager:
    global _manager
    if _manager is None:
        _manager = TurnManager()
    return _manager


def reset_turn_manager_for_tests() -> None:
    global _manager
    _manager = TurnManager()
