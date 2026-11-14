# tests/unit/test_nlp_low_confidence.py
"""Low-confidence parses must force clarification (never confirm)."""

from __future__ import annotations

import pytest

from app.nlp.schemas import ParsedMessage
from app.services.nlp_service import NLPService


@pytest.mark.asyncio
async def test_low_confidence_forces_clarification(db_session, test_user, monkeypatch):
    svc = NLPService(db_session)

    async def fake_chat(system, user, *, model=None):
        return (
            '{"type":"expense","amount":250,"description":"petrol",'
            '"category":"fuel","confidence":0.4,"needs_clarification":false}'
        )

    monkeypatch.setattr(svc, "_chat", fake_chat)
    parsed = await svc.parse(test_user.id, test_user.telegram_user_id, "petrol 250")
    assert parsed.needs_clarification is True
    assert parsed.clarification_question


@pytest.mark.asyncio
async def test_llm_total_failure_returns_clarify_not_raise(db_session, test_user, monkeypatch):
    from app.core.exceptions import NLPParseError

    svc = NLPService(db_session)

    async def boom(system, user, *, model=None):
        raise NLPParseError()

    monkeypatch.setattr(svc, "_chat", boom)
    parsed = await svc.parse(test_user.id, test_user.telegram_user_id, "xyz")
    assert parsed.needs_clarification is True
    assert parsed.type == "unknown"
