# app/repositories/user_repo.py
"""User persistence."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_user_id: str) -> Optional[User]:
        return await self.session.scalar(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )

    async def get_by_id(self, user_id: int) -> Optional[User]:
        return await self.session.scalar(select(User).where(User.id == user_id))

    async def create(
        self, telegram_user_id: str, telegram_username: str | None = None
    ) -> User:
        user = User(
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            name="",
            onboarded=False,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def list_active(self) -> list[User]:
        result = await self.session.scalars(
            select(User).where(User.is_active.is_(True), User.onboarded.is_(True))
        )
        return list(result.all())

    async def save(self, user: User) -> User:
        await self.session.flush()
        return user
