# app/services/audit_service.py
"""Dual-write: structured ops log + durable audit_log for money/security events."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.audit_repo import AuditRepository
from app.utils.logger import get_logger, get_request_id, log_event

logger = get_logger("flo.audit")

# Blueprint §24 — money/security events that must hit durable audit_log
_AUDIT_EVENTS = frozenset(
    {
        "user.created",
        "user.onboarded",
        "expense.created",
        "expense.edited",
        "expense.deleted",
        "expense.restored",
        "split.created",
        "debt.settled",
        "goal.created",
        "goal.contributed",
        "auth.login_success",
        "auth.login_failed",
        "injection.detected",
        "rate_limit.exceeded",
        "scope.blocked",
        "crisis.detected",
        "alert.triggered",
        "nlp.parse.failed",
        "llm.unavailable",
    }
)


class AuditService:
    """
    Ops log (stdout JSON) + durable audit_log for accountability.
    Does NOT commit — caller owns the transaction (flush only).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AuditRepository(session)

    async def record(
        self,
        event: str,
        *,
        user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        source: str | None = None,
        ip_address: str | None = None,
        level: int = logging.INFO,
        **extra: Any,
    ) -> None:
        log_event(
            logger,
            event,
            level=level,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            source=source,
            **extra,
        )
        if event not in _AUDIT_EVENTS:
            return
        payload = dict(new_value) if new_value is not None else (dict(extra) if extra else {})
        payload.setdefault("request_id", get_request_id())
        try:
            await self.repo.log(
                action=event,
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value=old_value,
                new_value=payload or None,
                source=source,
                ip_address=ip_address,
            )
            await self.session.flush()
        except Exception as e:
            log_event(
                logger,
                "audit.write_failed",
                level=logging.ERROR,
                error=str(e),
                original_event=event,
            )
