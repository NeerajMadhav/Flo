# app/nlp/fast_intent.py
"""
Deterministic intents for common chat phrases — skips the LLM when the ask
is unambiguous (list expenses, manage/delete, categories, help).
"""

from __future__ import annotations

import re

from app.nlp.schemas import ParsedMessage


def try_fast_intent(raw: str) -> ParsedMessage | None:
    """Return a ParsedMessage for clear query/manage phrases, else None."""
    text = (raw or "").strip()
    if not text or len(text) > 160:
        return None
    lower = text.lower()

    # Categories
    if re.search(r"\b(categories|category list|what categories)\b", lower):
        return ParsedMessage(
            type="query", query_intent="list_categories", confidence=0.95
        )

    # Delete last
    if re.search(
        r"\b(delete|remove|undo)\b.*\b(last|latest|recent)\b.*\b(expense|spend|entry)?\b",
        lower,
    ) or re.search(r"\b(delete|remove)\s+(the\s+)?last\b", lower):
        return ParsedMessage(
            type="query", query_intent="delete_last_expense", confidence=0.95
        )

    # List / show expenses (this month implied from welcome context)
    if re.search(
        r"\b(list|show|see|what are|those|my)\b.*\b(expenses?|spends?|transactions?)\b",
        lower,
    ) or re.search(
        r"\b(expenses?|spends?)\b.*\b(list|show|them)\b",
        lower,
    ):
        return ParsedMessage(
            type="query", query_intent="list_expenses", confidence=0.95
        )

    # Modify / edit existing
    if re.search(
        r"\b(modify|edit|change|update|correct|fix)\b.*\b(expense|spend|entry|existing)\b",
        lower,
    ) or re.search(
        r"\b(can i|how (do|can) i)\b.*\b(modify|edit|change|delete|update)\b",
        lower,
    ):
        return ParsedMessage(
            type="query", query_intent="manage_expenses", confidence=0.95
        )

    # Help
    if lower in {"help", "?", "what can you do", "commands"}:
        return ParsedMessage(type="query", query_intent="help", confidence=0.99)

    return None
