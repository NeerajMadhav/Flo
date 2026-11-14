# app/utils/currency.py
"""Indian currency formatting and amount parsing."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def format_inr(amount: Decimal | float | int | None) -> str:
    """Format as ₹1,23,456.78 (Indian grouping)."""
    if amount is None:
        return "₹0"
    d = Decimal(str(amount)).quantize(Decimal("0.01"))
    sign = "-" if d < 0 else ""
    d = abs(d)
    whole, frac = f"{d:.2f}".split(".")
    if len(whole) <= 3:
        grouped = whole
    else:
        last3 = whole[-3:]
        rest = whole[:-3]
        parts: list[str] = []
        while rest:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        grouped = ",".join(parts + [last3])
    return f"{sign}₹{grouped}.{frac}"


def parse_indian_amount(text: str) -> Decimal | None:
    """Parse 30k / 1.5L / 2 lakh / ₹250 / 1,00,000 into Decimal."""
    if not text:
        return None
    s = text.strip().lower().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "")
    s = s.replace("/-", "").strip()
    mult = Decimal("1")
    if s.endswith("lakh") or s.endswith("lakhs"):
        s = re.sub(r"\s*lakhs?\s*$", "", s).strip()
        mult = Decimal("100000")
    elif s.endswith("l"):
        s = s[:-1].strip()
        mult = Decimal("100000")
    elif s.endswith("k") or s.endswith("thousand"):
        s = re.sub(r"\s*(k|thousand)\s*$", "", s).strip()
        mult = Decimal("1000")
    try:
        return Decimal(s) * mult
    except (InvalidOperation, ValueError):
        return None
