# app/repositories/state_repo.py
"""Conversation state persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.models import ConversationState


class StateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, telegram_user_id: str) -> Optional[ConversationState]:
        return await self.session.scalar(
            select(ConversationState).where(
                ConversationState.telegram_user_id == telegram_user_id
            )
        )

    async def upsert(
        self,
        telegram_user_id: str,
        *,
        state: str,
        user_id: int | None = None,
        pending_data: dict[str, Any] | None = None,
        step_data: dict[str, Any] | None = None,
    ) -> ConversationState:
        row = await self.get(telegram_user_id)
        expiry = datetime.now(timezone.utc) + timedelta(
            minutes=get_settings().state_expiry_minutes
        )
        if row is None:
            row = ConversationState(
                telegram_user_id=telegram_user_id,
                user_id=user_id,
                state=state,
                pending_data=pending_data,
                step_data=step_data or {},
                expires_at=expiry,
            )
            self.session.add(row)
        else:
            row.state = state
            if user_id is not None:
                row.user_id = user_id
            row.pending_data = pending_data
            if step_data is not None:
                row.step_data = step_data
            row.expires_at = expiry
        await self.session.flush()
        return row

    async def clear_to_idle(self, telegram_user_id: str) -> ConversationState:
        """Idle + clear pending; keep recent_turns so follow-up chat retains context."""
        row = await self.get(telegram_user_id)
        turns = []
        if row and isinstance(row.step_data, dict):
            raw = row.step_data.get("recent_turns") or []
            if isinstance(raw, list):
                turns = raw
        step: dict[str, Any] = {"recent_turns": turns} if turns else {}
        return await self.upsert(
            telegram_user_id,
            state="IDLE",
            pending_data=None,
            step_data=step,
        )
