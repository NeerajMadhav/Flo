# tests/unit/test_heuristics.py
"""Heuristics are last-resort only — conversational phrases must NOT match."""

from __future__ import annotations

from decimal import Decimal

from app.nlp.heuristics import try_heuristic_parse


def test_simple_expense_ok():
    p = try_heuristic_parse("petrol 250")
    assert p is not None
    assert p.type == "expense"
    assert p.amount == Decimal("250")


def test_conversational_left_to_nlp():
    for phrase in (
        "Can you add the petrol 578",
        "Add petrol 578",
        "For petrol add 578",
        "please log my uber 500",
        "spent some money yesterday",
    ):
        assert try_heuristic_parse(phrase) is None, phrase


def test_amount_first():
    p = try_heuristic_parse("1.5k groceries")
    assert p is not None
    assert p.amount == Decimal("1500")
