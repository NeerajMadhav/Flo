# app/services/state_service.py
"""Conversation state machine with 30-minute expiry and recent turns."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ConversationState
from app.repositories.state_repo import StateRepository
from app.utils.logger import get_logger, log_event
from app.utils.sanitizer import sanitize_for_prompt

logger = get_logger("flo.state")

IDLE = "IDLE"
# Blueprint showed ~3 exchanges; keep last 8 messages (user+bot) for follow-ups
# like "same again" / "that was fuel" after chatting has started.
MAX_RECENT_TURNS = 8


class StateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = StateRepository(session)
        self.last_expired = False

    def _is_expired(self, row: ConversationState) -> bool:
        if row.expires_at is None:
            return False
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp < datetime.now(timezone.utc)

    @staticmethod
    def _turns_from(step_data: dict[str, Any] | None) -> list[dict[str, str]]:
        raw = (step_data or {}).get("recent_turns") or []
        out: list[dict[str, str]] = []
        for t in raw:
            if isinstance(t, dict) and t.get("text"):
                out.append(
                    {
                        "role": str(t.get("role") or "?"),
                        "text": str(t.get("text")),
                    }
                )
        return out

    def _merge_step(
        self,
        existing: dict[str, Any] | None,
        incoming: dict[str, Any] | None,
        *,
        keep_turns: bool = True,
    ) -> dict[str, Any]:
        """Merge step_data; always preserve recent_turns unless keep_turns=False."""
        base = dict(existing or {})
        turns = self._turns_from(base)
        merged = dict(base)
        if incoming is not None:
            merged.update(incoming)
        if keep_turns:
            # Incoming may omit recent_turns — restore preserved history
            if "recent_turns" not in (incoming or {}):
                merged["recent_turns"] = turns
            else:
                merged["recent_turns"] = self._turns_from(merged)[-MAX_RECENT_TURNS:]
        else:
            merged.pop("recent_turns", None)
        return merged

    async def get_state(self, telegram_user_id: str) -> ConversationState:
        """Fetch state; on flow expiry clear pending but keep chat history."""
        self.last_expired = False
        row = await self.repo.get(telegram_user_id)
        if row is None:
            row = await self.repo.upsert(telegram_user_id, state=IDLE, step_data={})
            await self.session.commit()
            return row
        if self._is_expired(row) and row.state != IDLE:
            previous = row.state
            preserved = {"recent_turns": self._turns_from(row.step_data)}
            row = await self.repo.upsert(
                telegram_user_id,
                state=IDLE,
                pending_data=None,
                step_data=preserved,
            )
            self.last_expired = True
            log_event(
                logger,
                "state.expired",
                telegram_user_id=telegram_user_id,
                previous_state=previous,
                user_id=row.user_id,
            )
            await self.session.commit()
        return row

    async def set_state(
        self,
        telegram_user_id: str,
        state: str,
        *,
        user_id: int | None = None,
        pending_data: dict[str, Any] | None = None,
        step_data: dict[str, Any] | None = None,
    ) -> ConversationState:
        row = await self.repo.get(telegram_user_id)
        existing_step = row.step_data if row else {}
        merged_step = self._merge_step(existing_step, step_data, keep_turns=True)
        row = await self.repo.upsert(
            telegram_user_id,
            state=state,
            user_id=user_id,
            pending_data=pending_data,
            step_data=merged_step,
        )
        await self.session.commit()
        return row

    async def go_idle(
        self, telegram_user_id: str, *, clear_history: bool = False
    ) -> ConversationState:
        """Return to IDLE. Keeps recent_turns so follow-up chat still has context."""
        row = await self.repo.get(telegram_user_id)
        turns = self._turns_from(row.step_data if row else None)
        step: dict[str, Any] = {}
        if not clear_history and turns:
            step["recent_turns"] = turns
        row = await self.repo.upsert(
            telegram_user_id,
            state=IDLE,
            pending_data=None,
            step_data=step,
        )
        await self.session.commit()
        return row

    async def append_turn(
        self, telegram_user_id: str, role: str, text: str
    ) -> None:
        """Append one user/bot utterance to rolling conversation context."""
        clean = sanitize_for_prompt(text, max_len=200)
        if not clean:
            return
        row = await self.get_state(telegram_user_id)
        step = dict(row.step_data or {})
        turns = self._turns_from(step)
        turns.append({"role": role, "text": clean})
        step["recent_turns"] = turns[-MAX_RECENT_TURNS:]
        await self.repo.upsert(
            telegram_user_id,
            state=row.state,
            pending_data=row.pending_data,
            step_data=step,
        )
        await self.session.commit()

    async def get_recent_context(self, telegram_user_id: str) -> str:
        row = await self.get_state(telegram_user_id)
        turns = self._turns_from(row.step_data)
        if not turns:
            return ""
        lines = [
            f"{t['role']}: {sanitize_for_prompt(t['text'], max_len=200)}" for t in turns
        ]
        return "\n".join(lines)
