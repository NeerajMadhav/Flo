# tests/unit/test_nlp_validate.py
from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.nlp.schemas import ParsedMessage
from app.nlp.validate import validate_parsed_for_write


def test_rejects_zero_amount():
    with pytest.raises(ValidationError):
        validate_parsed_for_write(
            ParsedMessage(type="expense", amount=Decimal("0"), confidence=1.0)
        )


def test_rejects_over_max():
    with pytest.raises(ValidationError):
        validate_parsed_for_write(
            ParsedMessage(type="expense", amount=Decimal("9999999"), confidence=1.0)
        )


def test_accepts_normal_expense():
    validate_parsed_for_write(
        ParsedMessage(
            type="expense",
            amount=Decimal("250"),
            date="2026-11-14",
            confidence=0.9,
        )
    )
