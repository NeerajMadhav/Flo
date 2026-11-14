# tests/unit/test_fast_intent.py
"""Deterministic intents for list / manage expenses."""

from __future__ import annotations

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
