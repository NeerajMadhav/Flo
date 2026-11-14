# tests/unit/test_onboarding_parse.py
"""Flexible onboarding name/amount extraction."""

from __future__ import annotations

from decimal import Decimal

from app.channels.telegram.handlers.onboarding import (
    _first_amount,
    _is_skip,
    _looks_like_name,
)


def test_reject_greeting_as_name():
    assert _looks_like_name("Hi") is None
    assert _looks_like_name("hello") is None


def test_name_from_sentence():
    assert _looks_like_name("My name is Neeraj") == "Neeraj"


def test_plain_name():
    assert _looks_like_name("Neeraj") == "Neeraj"


def test_income_anywhere_in_text():
    assert _first_amount("Any my income is 30k") == Decimal("30000")
    assert _first_amount("30000") == Decimal("30000")
    assert _is_skip("skip") is True
