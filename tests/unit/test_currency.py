# tests/unit/test_currency.py
"""Indian amount parse + INR format — all supported formats."""

from decimal import Decimal

import pytest

from app.utils.currency import format_inr, parse_indian_amount


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("250", Decimal("250")),
        ("₹250", Decimal("250")),
        ("Rs 250", Decimal("250")),
        ("rs.250", Decimal("250")),
        ("250/-", Decimal("250")),
        ("1,500", Decimal("1500")),
        ("1,00,000", Decimal("100000")),
        ("30k", Decimal("30000")),
        ("30K", Decimal("30000")),
        ("1.5k", Decimal("1500")),
        ("2L", Decimal("200000")),
        ("1.5L", Decimal("150000")),
        ("2 lakh", Decimal("200000")),
        ("3 lakhs", Decimal("300000")),
        ("50 thousand", Decimal("50000")),
        ("  420  ", Decimal("420")),
    ],
)
def test_parse_indian_amount_formats(raw, expected):
    assert parse_indian_amount(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "₹", None])
def test_parse_invalid_returns_none(raw):
    assert parse_indian_amount(raw) is None  # type: ignore[arg-type]


def test_format_inr_grouping():
    assert format_inr(Decimal("250")) == "₹250.00"
    assert format_inr(Decimal("1500")) == "₹1,500.00"
    assert format_inr(Decimal("123456.7")) == "₹1,23,456.70"
    assert format_inr(Decimal("-500")) == "-₹500.00"
    assert format_inr(None) == "₹0"
