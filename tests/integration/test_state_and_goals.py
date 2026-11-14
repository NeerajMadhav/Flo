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
    states = StateService(db_session)
    tg = test_user.telegram_user_id
    await states.go_idle(tg)
    for i in range(5):
        await states.append_turn(tg, "user", f"msg {i}")
    ctx = await states.get_recent_context(tg)
    # only last 3
    assert "msg 4" in ctx
    assert "msg 0" not in ctx
