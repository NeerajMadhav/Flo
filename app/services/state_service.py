# app/services/state_service.py
"""Conversation state machine with 30-minute expiry and recent turns."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ConversationState
from app.repositories.state_repo import StateRepository
from app.utils.logger import get_logger, log_event

logger = get_logger("flo.state")

IDLE = "IDLE"
MAX_RECENT_TURNS = 3


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

    async def get_state(self, telegram_user_id: str) -> ConversationState:
        """Fetch state; clear pending/recent on expiry and return IDLE."""
        self.last_expired = False
        row = await self.repo.get(telegram_user_id)
        if row is None:
            row = await self.repo.upsert(telegram_user_id, state=IDLE, step_data={})
            await self.session.commit()
            return row
        if self._is_expired(row) and row.state != IDLE:
            previous = row.state
            row = await self.repo.upsert(
                telegram_user_id,
                state=IDLE,
                pending_data=None,
                step_data={},
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
        row = await self.repo.upsert(
            telegram_user_id,
            state=state,
            user_id=user_id,
            pending_data=pending_data,
            step_data=step_data,
        )
        await self.session.commit()
        return row

    async def go_idle(self, telegram_user_id: str) -> ConversationState:
        row = await self.repo.clear_to_idle(telegram_user_id)
        await self.session.commit()
        return row

    async def append_turn(
        self, telegram_user_id: str, role: str, text: str
    ) -> None:
        from app.utils.sanitizer import sanitize_for_prompt

        row = await self.get_state(telegram_user_id)
        step = dict(row.step_data or {})
        turns = list(step.get("recent_turns") or [])
        turns.append({"role": role, "text": sanitize_for_prompt(text, max_len=200)})
        step["recent_turns"] = turns[-MAX_RECENT_TURNS:]
        await self.repo.upsert(
            telegram_user_id,
            state=row.state,
            pending_data=row.pending_data,
            step_data=step,
        )
        await self.session.commit()

    async def get_recent_context(self, telegram_user_id: str) -> str:
        from app.utils.sanitizer import sanitize_for_prompt

        row = await self.get_state(telegram_user_id)
        turns = (row.step_data or {}).get("recent_turns") or []
        if not turns:
            return ""
        lines = [
            f"{t.get('role', '?')}: {sanitize_for_prompt(str(t.get('text', '')), max_len=200)}"
            for t in turns
        ]
        return "\n".join(lines)
