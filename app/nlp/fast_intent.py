# app/nlp/fast_intent.py
"""
Deterministic intents for common chat phrases — works offline when OpenRouter
is rate-limited. Tolerates common typos (experiences→expenses, etc.).
"""

from __future__ import annotations

import re

from app.nlp.schemas import ParsedMessage

# Expense-ish tokens including frequent misspellings
_EXP = (
    r"(?:expenses?|expences?|experiences?|expens|spends?|spendings?|"
    r"transactions?|entries|logs?)"
)

# Category keywords → slugs (loose match in free text)
_CAT_HINTS: list[tuple[str, str]] = [
    (r"fuel|petrol|diesel|gas", "fuel"),
    (r"food|meal|lunch|dinner|breakfast|restaurant|swiggy|zomato", "food_outside"),
    (r"grocers?y|kirana|vegetables?", "food_groceries"),
    (r"uber|ola|cab|auto|metro|bus|transport", "transport"),
    (r"rent|house\s*rent", "rent"),
    (r"medical|medicine|doctor|hospital|pharmacy", "medical"),
    (r"shop|amazon|flipkart|myntra", "shopping"),
    (r"netflix|spotify|subscription", "subscriptions"),
    (r"electricity|water\s*bill|wifi|utility|utilities", "utilities"),
    (r"office", "office_expenses"),
]


def _normalize(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"\bexperiences?\b", "expenses", t)
    t = re.sub(r"\bexpences?\b", "expenses", t)
    t = re.sub(r"\bexpens\b", "expense", t)
    t = re.sub(r"\bspening\b", "spending", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _category_from_text(lower: str) -> str | None:
    for pat, slug in _CAT_HINTS:
        if re.search(rf"\b(?:{pat})\b", lower):
            return slug
    return None


def try_fast_intent(raw: str) -> ParsedMessage | None:
    """Return a ParsedMessage for clear query/manage phrases, else None."""
    text = (raw or "").strip()
    if not text or len(text) > 180:
        return None
    lower = _normalize(text)

    # Greeting (avoid LLM when models are 429'd)
    if re.fullmatch(r"(?:hi|hey|hello|yo|sup)(?:\s+(?:hi|hey|hello))*[!?.]*", lower):
        return ParsedMessage(type="greeting", confidence=0.99)

    # Categories list
    if re.search(r"\b(categories|category list|what categories|which categories)\b", lower):
        return ParsedMessage(
            type="query", query_intent="list_categories", confidence=0.95
        )

    # Count expenses
    if re.search(
        rf"\b(how many|count|number of|total number)\b.*\b{_EXP}\b",
        lower,
    ) or re.search(rf"\b{_EXP}\b.*\b(how many|count)\b", lower):
        return ParsedMessage(
            type="query", query_intent="count_expenses", confidence=0.95
        )

    # Breakdown / categorize
    if re.search(
        r"\b(break\s*down|breakdown|by category|categorize|categorise|group by)\b",
        lower,
    ) or (
        re.search(rf"\b{_EXP}\b", lower)
        and re.search(r"\b(by category|per category|categories)\b", lower)
    ):
        return ParsedMessage(
            type="query",
            query_intent="category_breakdown_month",
            confidence=0.95,
        )

    # Delete last
    if re.search(
        rf"\b(delete|remove|undo)\b.*\b(last|latest|recent)\b.*\b({_EXP}|entry)?\b",
        lower,
    ) or re.search(r"\b(delete|remove)\s+(the\s+)?last\b", lower):
        return ParsedMessage(
            type="query", query_intent="delete_last_expense", confidence=0.95
        )

    # Filter / list expenses — optional category hint
    cat = _category_from_text(lower)
    list_like = bool(
        re.search(
            rf"\b(list|show|see|what are|those|my|all)\b.*\b{_EXP}\b",
            lower,
        )
        or re.search(rf"\b{_EXP}\b.*\b(list|show|them|please)\b", lower)
        or re.search(rf"\b(filter|only)\b.*\b{_EXP}\b", lower)
    )
    # "fuel expenses" / "expenses on food"
    filter_like = bool(
        cat
        and re.search(rf"\b{_EXP}\b", lower)
        and re.search(r"\b(on|for|in|under|about)\b", lower)
    ) or bool(cat and re.search(rf"\b{_EXP}\b", lower) and len(lower.split()) <= 5)

    if list_like or filter_like:
        params = {"category": cat} if cat else {}
        return ParsedMessage(
            type="query",
            query_intent="list_expenses",
            query_params=params,
            confidence=0.95,
        )

    # Modify / edit existing
    if re.search(
        rf"\b(modify|edit|change|update|correct|fix)\b.*\b({_EXP}|entry|existing)\b",
        lower,
    ) or re.search(
        r"\b(can i|how (do|can) i)\b.*\b(modify|edit|change|delete|update)\b",
        lower,
    ):
        return ParsedMessage(
            type="query", query_intent="manage_expenses", confidence=0.95
        )

    # "add few expenses" / "add some bills" without amounts → ask for first line
    add_batch = bool(
        re.search(
            rf"\b(add|log|record|save)\b.*\b(few|some|several|multiple)\b.*\b({_EXP}|bills?)\b",
            lower,
        )
    )
    add_generic = bool(
        re.search(rf"\b(add|log)\b.*\b({_EXP}|bills?)\b", lower)
        and not re.search(r"\d", lower)
    )
    if add_batch or add_generic:
        return ParsedMessage(
            type="unknown",
            confidence=0.5,
            needs_clarification=True,
            clarification_question=(
                "Sure — send them one by one, like:\n"
                "• petrol 250\n• lunch 180\n• electricity 1200"
            ),
        )

    # Help
    if lower in {"help", "?", "what can you do", "commands"}:
        return ParsedMessage(type="query", query_intent="help", confidence=0.99)

    # Month spend total
    if re.search(
        r"\b(how much|total|spent|spend)\b.*\b(this month|month)\b",
        lower,
    ) or re.search(r"\b(this month('?s)? (spend|total|expenses?))\b", lower):
        return ParsedMessage(
            type="query", query_intent="total_spent_month", confidence=0.95
        )

    return None
