# app/channels/telegram/formatters.py
"""Human-readable Telegram message builders — clear shares + category emoji."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.core.exceptions import FloBaseException
from app.core.seed import DEFAULT_CATEGORIES
from app.nlp.schemas import ParsedMessage
from app.utils.currency import format_inr
from app.utils.text_utils import truncate_telegram

_CATEGORY_EMOJI: dict[str, str] = {
    slug: emoji for slug, _name, emoji, _order in DEFAULT_CATEGORIES
}
# Common aliases / custom slugs
_CATEGORY_EMOJI.update(
    {
        "office": "💼",
        "office_expenses": "💼",
        "bills": "🧾",
        "petrol": "⛽",
        "gas": "⛽",
        "cab": "🚕",
        "uber": "🚕",
        "ola": "🚕",
    }
)


def category_emoji(slug: str | None) -> str:
    """Relevant emoji for a category slug (⛽ fuel, 🍽️ food, …)."""
    key = (slug or "misc").strip().lower().replace(" ", "_")
    if key in _CATEGORY_EMOJI:
        return _CATEGORY_EMOJI[key]
    for part, emo in (
        ("fuel", "⛽"),
        ("petrol", "⛽"),
        ("food", "🍽️"),
        ("grocery", "🛒"),
        ("transport", "🚌"),
        ("rent", "🏠"),
        ("medical", "💊"),
        ("shop", "🛍️"),
        ("util", "💡"),
        ("sub", "📺"),
        ("travel", "✈️"),
        ("office", "💼"),
        ("bill", "🧾"),
    ):
        if part in key:
            return emo
    return "📝"


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


def _money(amount: Decimal) -> str:
    return format_inr(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _is_me_payer(payer: Any) -> bool:
    if payer is None:
        return True
    return str(payer).strip().lower() in ("", "me", "you", "i", "myself")


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
    emo = category_emoji(str(cat))
    return truncate_telegram(
        f"{emo} {desc}\n"
        f"────────────\n"
        f"Amount    {_money(_safe_amount(amount))}\n"
        f"Category  {cat}\n"
        f"Date      {date}\n"
        f"────────────\n"
        f"Save this?"
    )


def _equal_share(total: Decimal, n: int) -> Decimal:
    if n <= 0:
        n = 1
    return (total / Decimal(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_split_preview(data: dict[str, Any] | ParsedMessage) -> str:
    """Show per-person shares and who owes whom — not just 'equal with Surya'."""
    if isinstance(data, ParsedMessage):
        amount = data.amount
        desc = data.description or "Split"
        cat = data.category
        others = [p for p in (data.split_with or []) if str(p).strip()]
        payer = data.split_payer
        stype = (data.split_type or "equal").lower()
        amounts = dict(data.split_amounts or {})
        total_people = data.split_total_people
    else:
        amount = data.get("amount")
        desc = data.get("description") or "Split"
        cat = data.get("category")
        others = [p for p in (data.get("split_with") or []) if str(p).strip()]
        payer = data.get("split_payer")
        stype = str(data.get("split_type") or "equal").lower()
        amounts = dict(data.get("split_amounts") or {})
        total_people = data.get("split_total_people")

    total = _safe_amount(amount)
    emo = category_emoji(str(cat) if cat else desc)
    n = int(total_people) if total_people else (1 + len(others))
    if n < 2:
        n = max(2, 1 + len(others)) if others else 2

    share_lines: list[str] = []
    my_share = Decimal("0")
    other_shares: list[tuple[str, Decimal]] = []

    if stype in ("exact", "percent", "shares") and amounts:
        # Normalize keys; values are ₹ for exact
        def _amt_for(key: str) -> Decimal | None:
            for k, v in amounts.items():
                if str(k).strip().lower() == key.lower():
                    try:
                        return Decimal(str(v))
                    except (InvalidOperation, ValueError):
                        return None
            return None

        me_v = _amt_for("me") or _amt_for("you")
        if me_v is None and stype == "equal":
            me_v = _equal_share(total, n)
        if me_v is not None:
            my_share = me_v
            share_lines.append(f"• You: {_money(my_share)}")
        for p in others:
            pv = _amt_for(p)
            if pv is None:
                pv = _equal_share(total, n)
            other_shares.append((p, pv))
            share_lines.append(f"• {p}: {_money(pv)}")
    else:
        # Equal (default)
        share = _equal_share(total, n)
        my_share = share
        share_lines.append(f"• You: {_money(share)}")
        if others:
            for p in others:
                other_shares.append((p, share))
                share_lines.append(f"• {p}: {_money(share)}")
            named = 1 + len(others)
            if n > named:
                share_lines.append(f"• +{n - named} others: {_money(share)} each")
        else:
            share_lines.append(f"• Others ({n - 1}): {_money(share)} each")

    payer_me = _is_me_payer(payer)
    payer_label = "You" if payer_me else str(payer)
    owe_lines: list[str] = []
    if payer_me:
        for p, sh in other_shares:
            owe_lines.append(f"👉 {p} owes you {_money(sh)}")
    else:
        # Someone else paid the bill — you owe them your share
        owe_lines.append(f"👉 You owe {payer_label} {_money(my_share)}")

    body = (
        f"{emo} {desc}\n"
        f"────────────\n"
        f"Total     {_money(total)}\n"
        f"Paid by   {payer_label}\n"
        f"Split     {stype} · {n} people\n"
        f"\n"
        f"Shares\n"
        + "\n".join(share_lines)
    )
    if owe_lines:
        body += "\n\nWho owes\n" + "\n".join(owe_lines)
    body += "\n────────────\nSave this?"
    return truncate_telegram(body)


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
