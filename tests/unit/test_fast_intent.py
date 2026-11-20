# tests/unit/test_fast_intent.py
"""Deterministic intents — typos, count, filter, add-batch."""

from __future__ import annotations

from app.channels.telegram.handlers.settings import extract_name_update
from app.nlp.fast_intent import try_fast_intent


def test_list_expenses_phrases():
    for s in (
        "What are those expenses list them",
        "list expenses",
        "show my expenses",
    ):
        p = try_fast_intent(s)
        assert p is not None, s
        assert p.query_intent == "list_expenses"


def test_typo_experiences_means_expenses():
    p = try_fast_intent("How many experiences are there")
    assert p is not None
    assert p.query_intent == "count_expenses"


def test_how_many_expenses():
    p = try_fast_intent("How many expenses are there")
    assert p is not None
    assert p.query_intent == "count_expenses"


def test_filter_fuel():
    p = try_fast_intent("fuel expenses")
    assert p is not None
    assert p.query_intent == "list_expenses"
    assert p.query_params.get("category") == "fuel"


def test_add_few_clarifies():
    p = try_fast_intent("Can you add few expenses")
    assert p is not None
    assert p.needs_clarification is True


def test_manage_expenses():
    p = try_fast_intent("Can I modify the existing expenses")
    assert p is not None
    assert p.query_intent == "manage_expenses"


def test_delete_last():
    p = try_fast_intent("delete last expense")
    assert p is not None
    assert p.query_intent == "delete_last_expense"


def test_expense_log_not_hijacked():
    assert try_fast_intent("petrol 250") is None


def test_name_as_neeraj():
    assert extract_name_update("Can you save my name as neeraj") == "Neeraj"
    assert extract_name_update("save my name as neeraj") == "Neeraj"
