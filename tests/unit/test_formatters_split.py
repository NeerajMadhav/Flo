# tests/unit/test_formatters_split.py
"""Split preview must show per-person shares and who owes whom."""

from __future__ import annotations

from decimal import Decimal

from app.channels.telegram.formatters import category_emoji, format_split_preview
from app.nlp.schemas import ParsedMessage


def test_fuel_emoji():
    assert category_emoji("fuel") == "⛽"
    assert "⛽" in format_split_preview(
        ParsedMessage(
            type="split",
            amount=Decimal("578"),
            description="Fuel",
            category="fuel",
            split_with=["Surya"],
            split_type="equal",
        )
    )


def test_equal_split_shows_shares_and_owe():
    text = format_split_preview(
        ParsedMessage(
            type="split",
            amount=Decimal("578"),
            description="Fuel",
            category="fuel",
            split_payer=None,
            split_type="equal",
            split_with=["Surya"],
        )
    )
    assert "You:" in text
    assert "Surya:" in text
    assert "289" in text  # 578 / 2
    assert "owes you" in text.lower()
    assert "Surya" in text
    assert "Shares" in text
    assert "Who owes" in text
