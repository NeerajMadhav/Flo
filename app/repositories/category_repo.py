# app/repositories/category_repo.py
"""Category and user-correction persistence."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.models import Category, UserCategoryCorrection


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: int) -> list[Category]:
        result = await self.session.scalars(
            select(Category)
            .where(
                Category.is_active.is_(True),
                or_(Category.user_id.is_(None), Category.user_id == user_id),
            )
            .order_by(Category.sort_order)
        )
        return list(result.all())

    async def get_by_slug(self, slug: str, user_id: int | None = None) -> Optional[Category]:
        stmt = select(Category).where(Category.slug == slug, Category.is_active.is_(True))
        if user_id is not None:
            stmt = stmt.where(or_(Category.user_id.is_(None), Category.user_id == user_id))
        return await self.session.scalar(stmt)

    async def get_by_id(self, category_id: int) -> Optional[Category]:
        return await self.session.scalar(select(Category).where(Category.id == category_id))

    async def add_correction(
        self, user_id: int, keyword: str, category_id: int
    ) -> UserCategoryCorrection:
        existing = await self.session.scalar(
            select(UserCategoryCorrection).where(
                UserCategoryCorrection.user_id == user_id,
                UserCategoryCorrection.keyword == keyword.lower(),
            )
        )
        if existing:
            existing.correct_category_id = category_id
            await self.session.flush()
            return existing
        row = UserCategoryCorrection(
            user_id=user_id, keyword=keyword.lower(), correct_category_id=category_id
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_corrections(self, user_id: int) -> list[UserCategoryCorrection]:
        result = await self.session.scalars(
            select(UserCategoryCorrection)
            .options(selectinload(UserCategoryCorrection.category))
            .where(UserCategoryCorrection.user_id == user_id)
        )
        return list(result.all())
