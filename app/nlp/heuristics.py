# app/nlp/heuristics.py
"""
Last-resort parse when OpenRouter fails — NOT the primary NLU path.

Primary understanding is always the LLM (see NLPService.parse) so phrasing
can vary per user. These patterns only catch the simplest "desc + amount"
shapes so the bot still responds during free-tier outages.
"""

from __future__ import annotations

import re
from decimal import Decimal

from app.nlp.schemas import ParsedMessage
from app.utils.currency import parse_indian_amount

_EXPENSE_TAIL = re.compile(
    r"^([A-Za-z][A-Za-z\s.&'-]{0,60}?)\s+"
    r"(\d[\d,]*(?:\.\d+)?\s*(?:k|l|lakh|lakhs|thousand)?)\s*$",
    re.IGNORECASE,
)
_EXPENSE_HEAD = re.compile(
    r"^(\d[\d,]*(?:\.\d+)?\s*(?:k|l|lakh|lakhs|thousand)?)\s+"
    r"([A-Za-z][A-Za-z\s.&'-]{0,60})$",
    re.IGNORECASE,
)


def try_heuristic_parse(raw: str) -> ParsedMessage | None:
    """
    Emergency fallback only. Returns None for conversational / ambiguous text
    so the LLM (or a clarification) handles it.
    """
    text = (raw or "").strip()
    if not text or len(text) > 80:
        return None
    # Anything chatty / multi-intent → LLM. Heuristic is only "word(s) + amount".
    lower = text.lower()
    if any(
        w in lower
        for w in (
            "can you",
            "could you",
            "please",
            "pls",
            " add ",
            "log ",
            "record ",
            "for ",
            "i want",
            "i need",
            "help",
            "split",
            "paid",
            "owe",
            "save ",
            "how much",
            "the ",
        )
    ) or lower.startswith(("add ", "log ", "record ", "put ", "track ")):
        return None

    m = _EXPENSE_TAIL.match(text)
    if m:
        desc, amt_s = m.group(1).strip(), m.group(2).strip()
        amt = parse_indian_amount(amt_s)
        if amt and amt > 0 and 1 <= len(desc) <= 40:
            return ParsedMessage(
                type="expense", amount=amt, description=desc, confidence=0.85
            )

    m = _EXPENSE_HEAD.match(text)
    if m:
        amt = parse_indian_amount(m.group(1).strip())
        desc = m.group(2).strip()
        if amt and amt > 0 and 1 <= len(desc) <= 40:
            return ParsedMessage(
                type="expense", amount=amt, description=desc, confidence=0.85
            )

    return None
