# app/repositories/contact_repo.py
"""Contact / debt-balance persistence."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Contact


class ContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_name(self, user_id: int, name: str) -> Optional[Contact]:
        name_l = name.strip().lower()
        contacts = await self.list_for_user(user_id)
        for c in contacts:
            if c.canonical_name.lower() == name_l:
                return c
            aliases = c.aliases or []
            if any(str(a).lower() == name_l for a in aliases):
                return c
        return None

    async def list_for_user(self, user_id: int) -> list[Contact]:
        result = await self.session.scalars(
            select(Contact).where(Contact.user_id == user_id).order_by(Contact.canonical_name)
        )
        return list(result.all())

    async def list_with_balance(self, user_id: int) -> list[Contact]:
        result = await self.session.scalars(
            select(Contact).where(
                Contact.user_id == user_id,
                Contact.net_balance != 0,
            )
        )
        return list(result.all())

    async def get_or_create(self, user_id: int, name: str) -> Contact:
        existing = await self.get_by_name(user_id, name)
        if existing:
            return existing
        contact = Contact(user_id=user_id, canonical_name=name.strip(), aliases=[], net_balance=Decimal("0"))
        self.session.add(contact)
        await self.session.flush()
        return contact

    async def add_alias(self, contact: Contact, alias: str) -> Contact:
        aliases = list(contact.aliases or [])
        if alias.lower() not in [a.lower() for a in aliases]:
            aliases.append(alias)
            contact.aliases = aliases
            await self.session.flush()
        return contact

    async def adjust_balance(self, contact: Contact, delta: Decimal) -> Contact:
        """Atomically bump net_balance in SQL — safe under concurrent settlements."""
        from sqlalchemy import update

        await self.session.execute(
            update(Contact)
            .where(Contact.id == contact.id)
            .values(net_balance=Contact.net_balance + delta)
        )
        await self.session.refresh(contact)
        return contact
