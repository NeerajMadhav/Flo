# app/services/split_service.py
"""Four split types + bidirectional payer direction."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import atomic
from app.core.exceptions import SplitValidationError
from app.core.models import Expense, SplitParticipant
from app.repositories.contact_repo import ContactRepository
from app.repositories.expense_repo import ExpenseRepository
from app.repositories.split_repo import SplitRepository
from app.services.audit_service import AuditService
from app.services.category_service import CategoryService
from app.utils.date_utils import today_ist


def _money(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class SplitService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.expenses = ExpenseRepository(session)
        self.splits = SplitRepository(session)
        self.contacts = ContactRepository(session)
        self.categories = CategoryService(session)

    def calculate(
        self,
        *,
        total: Decimal,
        split_type: str,
        split_with: list[str],
        split_amounts: dict[str, float] | None = None,
        split_total_people: int | None = None,
        split_payer: str | None = None,
    ) -> tuple[Decimal, list[dict[str, Any]]]:
        """
        Return (user_share, participant_rows).
        participant_rows exclude 'me'; each has person_name, amount_owed, direction, raw_share.
        """
        split_amounts = split_amounts or {}
        they_paid = bool(split_payer and split_payer.lower() not in ("me", "i", "myself"))
        direction = "i_owe_them" if they_paid else "they_owe_me"
        names = [n for n in split_with if n.lower() not in ("me", "i")]

        if split_type in ("equal", None, ""):
            n = split_total_people or (len(names) + 1)
            if n < 2:
                raise SplitValidationError("Need at least 2 people for an equal split.")
            base = _money(total / Decimal(n))
            # Last share absorbs paise remainder so parts always sum to total
            shares = [base] * n
            shares[-1] = _money(total - base * (n - 1))

            if they_paid:
                user_share = shares[0]
                # Debt is to the payer for the user's share
                payer_name = split_payer or (names[0] if names else "someone")
                parts = [
                    {
                        "person_name": payer_name,
                        "amount_owed": user_share,
                        "raw_share": Decimal("1"),
                        "direction": "i_owe_them",
                    }
                ]
                return user_share, parts

            # User paid: index 0 = me, remaining shares map onto named others
            user_share = shares[0]
            other_shares = shares[1:]
            parts = []
            for i, name in enumerate(names):
                amt = other_shares[i] if i < len(other_shares) else base
                # If more names than remaining slots, last name absorbs leftover others
                if i == len(names) - 1 and len(other_shares) > len(names):
                    amt = _money(sum(other_shares[i:], Decimal("0")))
                parts.append(
                    {
                        "person_name": name,
                        "amount_owed": amt,
                        "raw_share": Decimal("1"),
                        "direction": "they_owe_me",
                    }
                )
            # If fewer names than (n-1), fold leftover into last named person
            if parts and len(other_shares) > len(names):
                parts[-1]["amount_owed"] = _money(
                    sum(other_shares[len(names) - 1 :], Decimal("0"))
                )
            elif not parts and n >= 2:
                raise SplitValidationError("Equal split needs at least one other person.")
            return user_share, parts

        if split_type in ("exact", "custom"):
            me = Decimal(str(split_amounts.get("me", split_amounts.get("Me", 0))))
            parts = []
            for name, amt in split_amounts.items():
                if name.lower() == "me":
                    continue
                parts.append(
                    {
                        "person_name": name,
                        "amount_owed": _money(Decimal(str(amt))),
                        "raw_share": Decimal(str(amt)),
                        "direction": direction,
                    }
                )
            total_parts = me + sum((p["amount_owed"] for p in parts), Decimal("0"))
            if abs(total_parts - total) > Decimal("0.05"):
                raise SplitValidationError(
                    f"Amounts add up to {total_parts}, not {total}."
                )
            return _money(me), parts

        if split_type in ("percent", "percentage"):
            parts = []
            me_pct = Decimal(str(split_amounts.get("me", split_amounts.get("Me", 0))))
            for name, pct in split_amounts.items():
                if name.lower() == "me":
                    continue
                amt = _money(total * Decimal(str(pct)) / Decimal("100"))
                parts.append(
                    {
                        "person_name": name,
                        "amount_owed": amt,
                        "raw_share": Decimal(str(pct)),
                        "direction": direction,
                    }
                )
            pct_sum = me_pct + sum(
                (Decimal(str(split_amounts[n])) for n in split_amounts if n.lower() != "me"),
                Decimal("0"),
            )
            if abs(pct_sum - Decimal("100")) > Decimal("0.5"):
                raise SplitValidationError(f"Percentages sum to {pct_sum}, not 100.")
            user_share = _money(total * me_pct / Decimal("100"))
            return user_share, parts

        if split_type == "shares":
            me_s = Decimal(str(split_amounts.get("me", split_amounts.get("Me", 1))))
            total_shares = me_s + sum(
                (
                    Decimal(str(v))
                    for k, v in split_amounts.items()
                    if k.lower() != "me"
                ),
                Decimal("0"),
            )
            if total_shares <= 0:
                raise SplitValidationError("Shares must be > 0.")
            unit = total / total_shares
            parts = []
            for name, s in split_amounts.items():
                if name.lower() == "me":
                    continue
                parts.append(
                    {
                        "person_name": name,
                        "amount_owed": _money(unit * Decimal(str(s))),
                        "raw_share": Decimal(str(s)),
                        "direction": direction,
                    }
                )
            user_share = _money(unit * me_s)
            return user_share, parts

        raise SplitValidationError(f"Unknown split type: {split_type}")

    async def create_split_expense(
        self,
        user_id: int,
        *,
        amount: Decimal,
        description: str | None,
        category_slug: str | None,
        expense_date=None,
        split_type: str = "equal",
        split_with: list[str],
        split_amounts: dict[str, float] | None = None,
        split_total_people: int | None = None,
        split_payer: str | None = None,
        raw_message: str | None = None,
        source: str = "telegram",
    ) -> Expense:
        user_share, parts = self.calculate(
            total=amount,
            split_type=split_type or "equal",
            split_with=split_with,
            split_amounts=split_amounts,
            split_total_people=split_total_people,
            split_payer=split_payer,
        )
        cat = await self.categories.resolve(category_slug, user_id)
        async with atomic(self.session):
            expense = Expense(
                user_id=user_id,
                amount=amount,
                category_id=cat.id,
                description=description,
                date=expense_date or today_ist(),
                is_split=True,
                split_type=split_type or "equal",
                raw_message=raw_message,
                source=source,
            )
            await self.expenses.create(expense)
            rows = [
                SplitParticipant(
                    expense_id=expense.id,
                    person_name=p["person_name"],
                    split_type=split_type or "equal",
                    raw_share=p["raw_share"],
                    amount_owed=p["amount_owed"],
                    user_share=user_share,
                    direction=p["direction"],
                )
                for p in parts
            ]
            await self.splits.add_many(rows)
            # Update contact balances
            for p in parts:
                contact = await self.contacts.get_or_create(user_id, p["person_name"])
                delta = p["amount_owed"] if p["direction"] == "they_owe_me" else -p["amount_owed"]
                await self.contacts.adjust_balance(contact, delta)
            await AuditService(self.session).record(
                "split.created",
                user_id=user_id,
                entity_type="expense",
                entity_id=expense.id,
                source=source,
                amount=str(amount),
                split_type=split_type or "equal",
                split_payer=split_payer,
                participants=len(parts),
            )
            return expense
