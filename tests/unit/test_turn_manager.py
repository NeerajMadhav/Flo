# tests/unit/test_turn_manager.py
"""TurnManager: queue independent asks, supersede cancels, merge fragments."""

from __future__ import annotations

import asyncio

import pytest

from app.core.turn_manager import TurnManager, reset_turn_manager_for_tests


@pytest.fixture(autouse=True)
def _fresh_manager():
    reset_turn_manager_for_tests()
    yield
    reset_turn_manager_for_tests()


@pytest.mark.asyncio
async def test_queue_two_independent_expenses():
    tm = TurnManager()
    t1 = await tm.collect("1", "petrol 250")
    assert t1 is not None
    assert t1.text == "petrol 250"

    t2 = await tm.collect("1", "lunch 180")
    assert t2 is None  # queued behind first

    nxt = await tm.finish(t1)
    assert nxt == "lunch 180"
    t3 = await tm.begin_queued("1", nxt)
    assert t3.text == "lunch 180"
    assert t3.alive(tm)


@pytest.mark.asyncio
async def test_supersede_halts_first_reply():
    tm = TurnManager()
    t1 = await tm.collect("1", "petrol 250")
    assert t1 is not None
    assert t1.alive(tm)

    absorbed = await tm.collect("1", "never mind")
    assert absorbed is None
    assert not t1.alive(tm)

    nxt = await tm.finish(t1)
    assert nxt == "never mind"


@pytest.mark.asyncio
async def test_fragment_while_busy_merges_and_reruns():
    tm = TurnManager()
    t1 = await tm.collect("1", "fuel 500")
    assert t1 is not None

    absorbed = await tm.collect("1", "with Rahul")
    assert absorbed is None
    assert not t1.alive(tm)

    nxt = await tm.finish(t1)
    assert nxt == "fuel 500 with Rahul"


@pytest.mark.asyncio
async def test_query_does_not_auto_supersede_expense():
    """Second clear ask queues; does not kill first unless cancel words."""
    tm = TurnManager()
    t1 = await tm.collect("1", "petrol 250")
    assert t1 is not None

    absorbed = await tm.collect("1", "list expenses")
    assert absorbed is None
    assert t1.alive(tm)  # still alive — queued, not superseded

    nxt = await tm.finish(t1)
    assert nxt == "list expenses"


@pytest.mark.asyncio
async def test_debounce_merges_two_fragments():
    tm = TurnManager()
    # Force non-clear short phrases into buffer
    t_a = asyncio.create_task(tm.collect("9", "also"))
    await asyncio.sleep(0.05)
    t_b = asyncio.create_task(tm.collect("9", "more"))
    a, b = await asyncio.gather(t_a, t_b)
    tickets = [t for t in (a, b) if t is not None]
    assert len(tickets) == 1
    assert "also" in tickets[0].text and "more" in tickets[0].text
