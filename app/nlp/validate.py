# app/nlp/validate.py
"""Server-side validation of LLM ParsedMessage — never trust the model alone."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.config import get_settings
from app.core.exceptions import ValidationError
from app.nlp.schemas import ParsedMessage
from app.utils.date_utils import today_ist


def validate_parsed_for_write(parsed: ParsedMessage) -> None:
    """
    Raise ValidationError if parsed output is unsafe to persist.
    Root cause: LLM can hallucinate huge amounts / future dates / empty settlements.
    """
    settings = get_settings()
    max_amt = Decimal(str(settings.max_amount_per_transaction))

    if parsed.type in ("expense", "split", "recurring"):
        if parsed.amount is None or parsed.amount <= 0:
            raise ValidationError("Amount must be greater than 0.")
        if parsed.amount > max_amt:
            raise ValidationError("Amount exceeds the maximum allowed.")

    if parsed.type == "settlement" and parsed.settled_amount is not None:
        if parsed.settled_amount <= 0:
            raise ValidationError("Settlement amount must be greater than 0.")
        if parsed.settled_amount > max_amt:
            raise ValidationError("Settlement amount exceeds the maximum allowed.")

    if parsed.date:
        try:
            d = date.fromisoformat(parsed.date)
        except ValueError as e:
            raise ValidationError("Invalid date.") from e
        today = today_ist()
        if d > today + timedelta(days=1):
            raise ValidationError("Future dates are not allowed.")
        if d < today - timedelta(days=365):
            raise ValidationError("Date is too far in the past.")

    if parsed.type == "split":
        if not parsed.split_with and not parsed.split_total_people:
            raise ValidationError("Split needs at least one other person.")
