# tests/unit/test_heuristics.py
"""Deterministic parse heuristics for clear user phrases."""

from __future__ import annotations

from decimal import Decimal

from app.nlp.heuristics import try_heuristic_parse


def test_expense_tail():
    p = try_heuristic_parse("petrol 250")
    assert p is not None
    assert p.type == "expense"
    assert p.amount == Decimal("250")


def test_expense_1_5k():
    p = try_heuristic_parse("1.5k groceries")
    assert p is not None
    assert p.amount == Decimal("1500")


def test_goal():
    p = try_heuristic_parse("save 50000 for new phone")
    assert p is not None
    assert p.type == "goal"
    assert p.goal_name == "new phone"


def test_settlement_they_pay():
    p = try_heuristic_parse("Rahul paid me 200")
    assert p is not None
    assert p.type == "settlement"
    assert p.settled_person == "Rahul"
    assert p.settlement_direction == "they_pay"


def test_split():
    p = try_heuristic_parse("lunch 600 split with Rahul")
    assert p is not None
    assert p.type == "split"
    assert p.split_with == ["Rahul"]


def test_paid_for_is_expense_not_settlement():
    p = try_heuristic_parse("paid 500 for the uber to office")
    assert p is not None
    assert p.type == "expense"
    assert p.amount == Decimal("500")


def test_ambiguous_returns_none():
    assert try_heuristic_parse("spent some money yesterday") is None


def test_amount_on_desc():
    p = try_heuristic_parse("400 on snacks")
    assert p is not None
    assert p.type == "expense"
    assert p.amount == Decimal("400")
    assert "snack" in (p.description or "").lower()
