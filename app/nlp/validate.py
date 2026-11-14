# app/nlp/validate.py
"""Server-side validation of LLM ParsedMessage — never trust the model alone."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.config import get_settings
from app.core.exceptions import ValidationError
from app.nlp.schemas import ParsedMessage
from app.utils.date_utils import today_ist
from app.utils.guardrails import GuardrailCode, explain


def validate_parsed_for_write(parsed: ParsedMessage) -> None:
    """
    Raise ValidationError with a named guardrail explanation if unsafe to persist.
    Root cause: LLM can hallucinate huge amounts / future dates / empty settlements.
    """
    settings = get_settings()
    max_amt = Decimal(str(settings.max_amount_per_transaction))

    if parsed.type in ("expense", "split", "recurring"):
        if parsed.amount is None:
            raise ValidationError(explain(GuardrailCode.AMOUNT_MISSING))
        if parsed.amount <= 0:
            raise ValidationError(explain(GuardrailCode.AMOUNT_NOT_POSITIVE))
        if parsed.amount > max_amt:
            raise ValidationError(
                explain(GuardrailCode.AMOUNT_TOO_HIGH, max_amount=f"{max_amt:,.0f}")
            )

    if parsed.type == "settlement":
        if not (parsed.settled_person or "").strip():
            raise ValidationError(explain(GuardrailCode.SETTLEMENT_NO_PERSON))
        if parsed.settled_amount is not None:
            if parsed.settled_amount <= 0:
                raise ValidationError(explain(GuardrailCode.AMOUNT_NOT_POSITIVE))
            if parsed.settled_amount > max_amt:
                raise ValidationError(
                    explain(
                        GuardrailCode.AMOUNT_TOO_HIGH, max_amount=f"{max_amt:,.0f}"
                    )
                )

    if parsed.date:
        try:
            d = date.fromisoformat(parsed.date)
        except ValueError as e:
            raise ValidationError(explain(GuardrailCode.DATE_INVALID)) from e
        today = today_ist()
        if d > today + timedelta(days=1):
            raise ValidationError(explain(GuardrailCode.DATE_FUTURE))
        if d < today - timedelta(days=365):
            raise ValidationError(explain(GuardrailCode.DATE_TOO_OLD))

    if parsed.type == "split":
        if not parsed.split_with and not parsed.split_total_people:
            raise ValidationError(explain(GuardrailCode.SPLIT_NO_PEOPLE))
