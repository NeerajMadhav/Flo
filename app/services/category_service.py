# app/services/category_service.py
"""Category resolution and user correction injection."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CategoryNotFoundError
from app.core.models import Category
from app.repositories.category_repo import CategoryRepository


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CategoryRepository(session)

    async def get_categories_for_prompt(self, user_id: int) -> str:
        cats = await self.repo.list_for_user(user_id)
        return ", ".join(c.slug for c in cats)

    async def get_user_corrections_for_prompt(self, user_id: int) -> str:
        rows = await self.repo.list_corrections(user_id)
        if not rows:
            return ""
        lines = []
        for r in rows:
            slug = r.category.slug if r.category else str(r.correct_category_id)
            lines.append(f'- "{r.keyword}" → {slug}')
        return "\n".join(lines)

    async def resolve(self, slug: str | None, user_id: int) -> Category:
        if not slug:
            cat = await self.repo.get_by_slug("misc", user_id)
            if not cat:
                raise CategoryNotFoundError("misc")
            return cat
        cat = await self.repo.get_by_slug(slug, user_id)
        if not cat:
            cat = await self.repo.get_by_slug("misc", user_id)
        if not cat:
            raise CategoryNotFoundError(slug)
        return cat

    async def record_correction(self, user_id: int, keyword: str, category_slug: str) -> None:
        cat = await self.resolve(category_slug, user_id)
        await self.repo.add_correction(user_id, keyword, cat.id)
        await self.session.commit()

    async def list_display(self, user_id: int) -> list[Category]:
        return await self.repo.list_for_user(user_id)
