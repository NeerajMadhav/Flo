# app/channels/telegram/formatters.py
"""Human-readable Telegram message builders."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.exceptions import FloBaseException
from app.nlp.schemas import ParsedMessage
from app.utils.currency import format_inr
from app.utils.text_utils import truncate_telegram


def format_error(exc: Exception) -> str:
    if isinstance(exc, FloBaseException):
        return exc.message
    return "Something went wrong. Try again."


def _safe_amount(amount: Any) -> Decimal:
    if amount is None:
        return Decimal("0")
    try:
        return Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def format_expense_preview(data: dict[str, Any] | ParsedMessage) -> str:
    if isinstance(data, ParsedMessage):
        amount = data.amount
        desc = data.description or "Expense"
        cat = data.category or "misc"
        date = data.date or "today"
    else:
        amount = data.get("amount")
        desc = data.get("description") or "Expense"
        cat = data.get("category") or "misc"
        date = data.get("date") or "today"
    return truncate_telegram(
        f"📝 {desc}\nAmount: {format_inr(_safe_amount(amount))}\n"
        f"Category: {cat}\nDate: {date}\n\nSave this?"
    )


def format_split_preview(data: dict[str, Any] | ParsedMessage) -> str:
    if isinstance(data, ParsedMessage):
        amount = data.amount
        desc = data.description or "Split"
        people = ", ".join(data.split_with) or "friends"
        payer = data.split_payer or "You"
        stype = data.split_type or "equal"
    else:
        amount = data.get("amount")
        desc = data.get("description") or "Split"
        people = ", ".join(data.get("split_with") or []) or "friends"
        payer = data.get("split_payer") or "You"
        stype = data.get("split_type") or "equal"
    return truncate_telegram(
        f"🧾 {desc} {format_inr(_safe_amount(amount))}\n"
        f"Paid by: {payer}\nSplit ({stype}) with: {people}\n\nSave this?"
    )


def format_settlement_preview(data: dict[str, Any] | ParsedMessage) -> str:
    if isinstance(data, ParsedMessage):
        person = data.settled_person or "?"
        amount = data.settled_amount
        direction = data.settlement_direction
    else:
        person = data.get("settled_person") or "?"
        amount = data.get("settled_amount")
        direction = data.get("settlement_direction")
    if direction in ("i_pay", "i_paid_them"):
        verb = f"You paid {person}"
    else:
        verb = f"{person} paid you"
    amt = format_inr(Decimal(str(amount))) if amount is not None else "full balance"
    return f"💸 {verb} {amt}. Confirm?"
