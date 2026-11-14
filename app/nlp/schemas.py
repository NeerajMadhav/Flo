# app/nlp/schemas.py
"""ParsedMessage schema returned by NLPService."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ParsedMessage(BaseModel):
    """Structured output from the finance parser LLM."""

    type: Literal[
        "expense",
        "split",
        "settlement",
        "query",
        "goal",
        "recurring",
        "correction",
        "greeting",
        "unknown",
        "command",
    ] = "unknown"
    amount: Optional[Decimal] = None
    description: Optional[str] = None
    category: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD
    split_payer: Optional[str] = None
    split_type: Optional[str] = None
    split_with: list[str] = Field(default_factory=list)
    split_amounts: dict[str, float] = Field(default_factory=dict)
    split_total_people: Optional[int] = None
    settled_person: Optional[str] = None
    settled_amount: Optional[Decimal] = None
    settlement_direction: Optional[str] = None  # i_pay | they_pay
    query_intent: Optional[str] = None
    query_params: dict[str, Any] = Field(default_factory=dict)
    goal_name: Optional[str] = None
    goal_action: Optional[str] = None
    goal_amount: Optional[Decimal] = None
    recurrence: Optional[dict[str, Any]] = None
    upi_ref: Optional[str] = None
    is_recurring_hint: bool = False
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: Optional[str] = None

    # Convenience aliases used by older plan naming
    @property
    def is_split(self) -> bool:
        return self.type == "split"
