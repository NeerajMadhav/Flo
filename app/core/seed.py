# app/core/seed.py
"""Seed default expense categories into the database."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, create_all_tables
from app.core.models import Category

DEFAULT_CATEGORIES: list[tuple[str, str, str, int]] = [
    ("food_outside", "Food (Outside)", "🍽️", 10),
    ("food_delivery", "Food Delivery", "🛵", 20),
    ("food_groceries", "Groceries", "🛒", 30),
    ("fuel", "Fuel", "⛽", 40),
    ("transport", "Transport", "🚌", 50),
    ("entertainment", "Entertainment", "🎬", 60),
    ("shopping", "Shopping", "🛍️", 70),
    ("subscriptions", "Subscriptions", "📺", 80),
    ("utilities", "Utilities", "💡", 90),
    ("rent", "Rent", "🏠", 100),
    ("emi", "EMI / Loan", "🏦", 110),
    ("medical", "Medical", "💊", 120),
    ("travel", "Travel", "✈️", 130),
    ("education", "Education", "📚", 140),
    ("personal_care", "Personal Care", "💇", 150),
    ("gifts", "Gifts", "🎁", 160),
    ("misc", "Miscellaneous", "📦", 999),
]


async def seed_categories() -> None:
    """Insert default categories if they do not already exist."""
    await create_all_tables()
    async with AsyncSessionLocal() as session:
        for slug, name, emoji, order in DEFAULT_CATEGORIES:
            existing = await session.scalar(
                select(Category).where(Category.slug == slug, Category.user_id.is_(None))
            )
            if existing:
                continue
            session.add(
                Category(
                    slug=slug,
                    display_name=name,
                    icon_emoji=emoji,
                    is_default=True,
                    user_id=None,
                    sort_order=order,
                )
            )
        await session.commit()
        print(f"Seeded {len(DEFAULT_CATEGORIES)} default categories.")


if __name__ == "__main__":
    asyncio.run(seed_categories())
