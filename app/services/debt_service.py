# app/services/debt_service.py
"""Settlements and net-balance views."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import atomic
from app.core.exceptions import ContactNotFoundError, ValidationError
from app.core.models import Contact
from app.repositories.contact_repo import ContactRepository
from app.repositories.debt_repo import DebtRepository
from app.repositories.split_repo import SplitRepository
from app.services.audit_service import AuditService
from app.utils.currency import format_inr


class DebtService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.contacts = ContactRepository(session)
        self.debts = DebtRepository(session)
        self.splits = SplitRepository(session)

    async def who_owes_me(self, user_id: int) -> list[Contact]:
        contacts = await self.contacts.list_with_balance(user_id)
        return [c for c in contacts if Decimal(c.net_balance) > 0]

    async def i_owe_who(self, user_id: int) -> list[Contact]:
        contacts = await self.contacts.list_with_balance(user_id)
        return [c for c in contacts if Decimal(c.net_balance) < 0]

    async def contact_balance(self, user_id: int, name: str) -> Contact:
        c = await self.contacts.get_by_name(user_id, name)
        if not c:
            raise ContactNotFoundError(name)
        return c

    async def settle(
        self,
        user_id: int,
        person_name: str,
        amount: Decimal | None,
        direction: str,
    ) -> Contact:
        """
        direction: they_pay (they paid me) | i_pay (I paid them).
        Marks unsettled splits FIFO and adjusts net_balance.
        """
        contact = await self.contacts.get_or_create(user_id, person_name)
        if amount is not None and amount <= 0:
            raise ValidationError("Settlement amount must be > 0.")

        async with atomic(self.session):
            unsettled = await self.debts.unsettled_for_contact(user_id, contact.canonical_name)
            # Also match aliases
            if not unsettled:
                for alias in contact.aliases or []:
                    unsettled = await self.debts.unsettled_for_contact(user_id, str(alias))
                    if unsettled:
                        break

            remaining = amount
            if remaining is None:
                # Full settle in the stated direction
                for row in unsettled:
                    if direction == "they_pay" and row.direction == "they_owe_me":
                        await self.splits.mark_settled(row)
                    elif direction == "i_pay" and row.direction == "i_owe_them":
                        await self.splits.mark_settled(row)
                if direction == "they_pay":
                    # Zero out positive balance owed to me
                    if contact.net_balance > 0:
                        await self.contacts.adjust_balance(contact, -contact.net_balance)
                else:
                    if contact.net_balance < 0:
                        await self.contacts.adjust_balance(contact, -contact.net_balance)
            else:
                for row in unsettled:
                    if remaining <= 0:
                        break
                    match = (direction == "they_pay" and row.direction == "they_owe_me") or (
                        direction == "i_pay" and row.direction == "i_owe_them"
                    )
                    if not match:
                        continue
                    if row.amount_owed <= remaining:
                        remaining -= Decimal(row.amount_owed)
                        await self.splits.mark_settled(row)
                    else:
                        # Partial: reduce amount_owed, don't fully settle
                        row.amount_owed = Decimal(row.amount_owed) - remaining
                        remaining = Decimal("0")
                        await self.session.flush()
                paid = amount - remaining
                delta = -paid if direction == "they_pay" else paid
                # they_pay reduces what they owe me (negative delta on positive balance)
                # i_pay reduces what I owe (positive delta on negative balance)
                if direction == "they_pay":
                    await self.contacts.adjust_balance(contact, -paid)
                else:
                    await self.contacts.adjust_balance(contact, paid)

            await AuditService(self.session).record(
                "debt.settled",
                user_id=user_id,
                entity_type="contact",
                entity_id=contact.id,
                new_value={
                    "person": contact.canonical_name,
                    "direction": direction,
                    "amount": str(amount) if amount is not None else "full",
                    "net_balance": str(contact.net_balance),
                },
                source="telegram",
            )

        await self.session.refresh(contact)
        return contact

    def format_balance_line(self, contact: Contact) -> str:
        bal = Decimal(contact.net_balance)
        if bal > 0:
            return f"{contact.canonical_name} owes you {format_inr(bal)}"
        if bal < 0:
            return f"You owe {contact.canonical_name} {format_inr(abs(bal))}"
        return f"Settled up with {contact.canonical_name}"
