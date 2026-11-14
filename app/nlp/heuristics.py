# app/nlp/heuristics.py
"""
Deterministic high-confidence parses for clear phrases.
Used before OpenRouter so free-tier rate limits / outages don't break common paths.
"""

from __future__ import annotations

import re
from decimal import Decimal

from app.nlp.schemas import ParsedMessage
from app.utils.currency import parse_indian_amount

_GOAL = re.compile(
    r"^(?:save|set\s+aside|put\s+aside)\s+(.+?)\s+for\s+(.+)$",
    re.IGNORECASE,
)
_SETTLE_THEY = re.compile(
    r"^(.+?)\s+paid\s+me\s+(.+)$",
    re.IGNORECASE,
)
_SETTLE_I = re.compile(
    r"^(?:i\s+)?paid\s+(.+?)\s+(.+)$",
    re.IGNORECASE,
)
_SPLIT = re.compile(
    r"^(.+?)\s+(.+?)\s+split\s+with\s+(.+)$",
    re.IGNORECASE,
)
_EXPENSE_TAIL = re.compile(
    r"^(.+?)\s+(\d[\d,]*(?:\.\d+)?\s*(?:k|l|lakh|lakhs|thousand)?)\s*(?:rs\.?|rupees?)?$",
    re.IGNORECASE,
)
_EXPENSE_HEAD = re.compile(
    r"^(\d[\d,]*(?:\.\d+)?\s*(?:k|l|lakh|lakhs|thousand)?)\s+(?:on\s+|for\s+)?(.+)$",
    re.IGNORECASE,
)
_SAME_AGAIN = re.compile(
    r"^(same(?:\s+again)?|again|same\s+thing|one\s+more)$",
    re.IGNORECASE,
)
_QUERY_MONTH = re.compile(
    r"how\s+much\s+(?:did\s+i\s+)?spend(?:\s+this\s+month)?",
    re.IGNORECASE,
)
_WHO_OWES = re.compile(r"who\s+owes\s+me", re.IGNORECASE)
_GREETING = re.compile(r"^(hi|hey|hello|yo|sup)\b", re.IGNORECASE)


def try_heuristic_parse(raw: str) -> ParsedMessage | None:
    """Return a ParsedMessage when the phrase is unambiguous; else None."""
    text = (raw or "").strip()
    if not text or len(text) > 200:
        return None

    if _GREETING.match(text) and len(text) < 20:
        return ParsedMessage(type="greeting", confidence=0.99)

    if _WHO_OWES.search(text):
        return ParsedMessage(
            type="query", query_intent="who_owes_me", confidence=0.99
        )

    if _QUERY_MONTH.search(text):
        return ParsedMessage(
            type="query",
            query_intent="total_spent_month",
            confidence=0.99,
        )

    m = _GOAL.match(text)
    if m:
        amt = parse_indian_amount(m.group(1).strip())
        name = m.group(2).strip()
        if amt and amt > 0 and len(name) >= 2:
            return ParsedMessage(
                type="goal",
                goal_action="set",
                goal_name=name[:64],
                goal_amount=str(amt),
                confidence=0.98,
            )

    m = _SETTLE_THEY.match(text)
    if m:
        person = m.group(1).strip()
        amt = parse_indian_amount(m.group(2).strip())
        if person and len(person) < 40 and amt and amt > 0:
            return ParsedMessage(
                type="settlement",
                settled_person=person.title(),
                settled_amount=amt,
                settlement_direction="they_pay",
                confidence=0.97,
            )

    m = _SETTLE_I.match(text)
    if m and "split" not in text.lower():
        person = m.group(1).strip()
        amt = parse_indian_amount(m.group(2).strip())
        # Avoid "paid 500 for the uber" matching settlement
        if (
            person
            and not person.lower().startswith("for ")
            and " for " not in person.lower()
            and len(person) < 40
            and amt
            and amt > 0
        ):
            return ParsedMessage(
                type="settlement",
                settled_person=person.title(),
                settled_amount=amt,
                settlement_direction="i_pay",
                confidence=0.95,
            )

    m = _SPLIT.match(text)
    if m:
        left, amt_s, people_s = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        # left may be "lunch" and amt "600", or left "lunch 600" if regex greedy — fix:
        amt = parse_indian_amount(amt_s)
        desc = left
        if amt is None:
            # try "lunch 600" in left+amt combined
            combo = f"{left} {amt_s}"
            m2 = _EXPENSE_TAIL.match(combo)
            if m2:
                desc = m2.group(1).strip()
                amt = parse_indian_amount(m2.group(2).strip())
        names = [
            n.strip()
            for n in re.split(r",| and | & |/", people_s, flags=re.IGNORECASE)
            if n.strip()
        ]
        if amt and amt > 0 and names:
            return ParsedMessage(
                type="split",
                amount=amt,
                description=desc,
                split_with=names,
                split_type="equal",
                split_total_people=len(names) + 1,
                confidence=0.96,
            )

    m = _EXPENSE_TAIL.match(text)
    if m and "split" not in text.lower() and "paid" not in text.lower():
        desc = m.group(1).strip()
        amt = parse_indian_amount(m.group(2).strip())
        if amt and amt > 0 and 1 <= len(desc) <= 80:
            return ParsedMessage(
                type="expense",
                amount=amt,
                description=desc,
                confidence=0.95,
            )

    m = _EXPENSE_HEAD.match(text)
    if m and "split" not in text.lower() and "paid" not in text.lower():
        amt = parse_indian_amount(m.group(1).strip())
        desc = m.group(2).strip()
        if amt and amt > 0 and 1 <= len(desc) <= 80:
            return ParsedMessage(
                type="expense",
                amount=amt,
                description=desc,
                confidence=0.95,
            )

    # Indirect: "paid 500 for the uber to office"
    m = re.match(
        r"^(?:paid|spent)\s+(.+?)\s+for\s+(?:the\s+)?(.+)$",
        text,
        re.IGNORECASE,
    )
    if m:
        amt = parse_indian_amount(m.group(1).strip())
        desc = m.group(2).strip()
        if amt and amt > 0 and desc:
            return ParsedMessage(
                type="expense",
                amount=amt,
                description=desc,
                confidence=0.93,
            )

    return None
