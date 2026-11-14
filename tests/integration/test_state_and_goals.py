# tests/integration/test_state_and_goals.py
"""State expiry, welcome-back context, goals duplicate rejection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.exceptions import GoalAlreadyExistsError
from app.services.goal_service import GoalService
from app.services.state_service import StateService
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_state_expiry_clears_to_idle(db_session, test_user):
    states = StateService(db_session)
    await states.set_state(
        test_user.telegram_user_id,
        "CONFIRM_EXPENSE",
        user_id=test_user.id,
        pending_data={"amount": "100"},
        step_data={"recent_turns": [{"role": "user", "text": "old"}]},
    )
    row = await states.get_state(test_user.telegram_user_id)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    refreshed = await states.get_state(test_user.telegram_user_id)
    assert refreshed.state == "IDLE"
    assert refreshed.pending_data is None
    # Chat history survives flow expiry so follow-ups still have context
    assert refreshed.step_data.get("recent_turns")
    assert refreshed.step_data["recent_turns"][0]["text"] == "old"


@pytest.mark.asyncio
async def test_prompt_context_and_welcome(db_session, test_user):
    users = UserService(db_session)
    ctx = await users.get_prompt_context(test_user.id)
    assert "Arjun" in ctx
    welcome = await users.get_welcome_back_summary(test_user.id)
    assert "Welcome back" in welcome


@pytest.mark.asyncio
async def test_goal_create_contribute_duplicate(db_session, test_user):
    goals = GoalService(db_session)
    g = await goals.create(test_user.id, "Phone", Decimal("50000"))
    assert g.current_amount == Decimal("0")
    g2 = await goals.contribute(test_user.id, "Phone", Decimal("5000"))
    assert g2.current_amount == Decimal("5000")
    with pytest.raises(GoalAlreadyExistsError):
        await goals.create(test_user.id, "Phone", Decimal("1000"))


@pytest.mark.asyncio
async def test_recent_turns_capped(db_session, test_user):
    from app.services.state_service import MAX_RECENT_TURNS

    states = StateService(db_session)
    tg = test_user.telegram_user_id
    await states.go_idle(tg)
    for i in range(MAX_RECENT_TURNS + 2):
        await states.append_turn(tg, "user", f"msg {i}")
    ctx = await states.get_recent_context(tg)
    assert f"msg {MAX_RECENT_TURNS + 1}" in ctx
    assert "msg 0" not in ctx
    assert "msg 1" not in ctx


@pytest.mark.asyncio
async def test_conversation_context_survives_idle_and_bot_turns(db_session, test_user):
    """After chatting starts, user+bot turns stay available for NLP follow-ups."""
    states = StateService(db_session)
    tg = test_user.telegram_user_id
    await states.append_turn(tg, "user", "coffee 80")
    await states.append_turn(tg, "bot", "Saved ✅ coffee — 80")
    await states.set_state(
        tg, "CONFIRM_EXPENSE", user_id=test_user.id, pending_data={"amount": "80"}
    )
    await states.go_idle(tg)
    ctx = await states.get_recent_context(tg)
    assert "user: coffee 80" in ctx
    assert "bot: Saved ✅ coffee — 80" in ctx
    # set_state without recent_turns must not wipe history
    await states.set_state(tg, "CLARIFYING", user_id=test_user.id, step_data={"q": "x"})
    ctx2 = await states.get_recent_context(tg)
    assert "coffee 80" in ctx2


@pytest.mark.asyncio
async def test_nlp_parse_prompt_includes_prior_user_and_bot(db_session, test_user, monkeypatch):
    """E2E: after a logged exchange + go_idle, next parse prompt still has both turns."""
    from app.services.nlp_service import NLPService

    states = StateService(db_session)
    tg = test_user.telegram_user_id
    await states.append_turn(tg, "user", "coffee 80")
    await states.append_turn(tg, "bot", "Saved coffee 80")
    await states.go_idle(tg)

    captured: dict[str, str] = {}

    async def fake_chat(system, user_msg, *, chain=None, model=None):
        captured["system"] = system
        return (
            '{"type":"expense","amount":80,"description":"coffee",'
            '"category":"food_outside","confidence":0.9}'
        )

    nlp = NLPService(db_session)
    monkeypatch.setattr(nlp, "_chat", fake_chat)
    parsed = await nlp.parse(test_user.id, tg, "same again")
    assert parsed.type == "expense"
    assert "coffee 80" in captured["system"]
    assert "bot: Saved coffee 80" in captured["system"]
    assert "user: coffee 80" in captured["system"]


@pytest.mark.asyncio
async def test_remember_bot_reply_writes_via_session_factory(
    db_session, test_user, monkeypatch
):
    """Handler memory helper must persist bot turns into the same DB the app uses."""
    from contextlib import asynccontextmanager

    from app.channels.telegram import memory as memory_mod
    from app.services.state_service import StateService

    @asynccontextmanager
    async def _session_cm():
        yield db_session

    # AsyncSessionLocal() is used as `async with AsyncSessionLocal() as session`
    class _Factory:
        def __call__(self):
            return _session_cm()

    monkeypatch.setattr(memory_mod, "AsyncSessionLocal", _Factory())
    tg = test_user.telegram_user_id
    await StateService(db_session).append_turn(tg, "user", "petrol 250")
    await memory_mod.remember_bot_reply(tg, "Saved petrol 250")
    ctx = await StateService(db_session).get_recent_context(tg)
    assert "user: petrol 250" in ctx
    assert "bot: Saved petrol 250" in ctx


@pytest.mark.asyncio
async def test_remember_bot_reply_does_not_raise_on_db_error(monkeypatch):
    """Post-reply memory failure must not break the user-facing turn."""
    from app.channels.telegram import memory as memory_mod

    class _Boom:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(memory_mod, "AsyncSessionLocal", _Boom())
    await memory_mod.remember_bot_reply("999", "hello")  # must not raise
