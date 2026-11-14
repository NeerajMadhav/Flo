# scripts/_neon_seed.py
"""Seed default categories on Neon after create_all."""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.core.database import AsyncSessionLocal, create_all_tables, engine
from app.core.seed import seed_categories


async def main() -> None:
    get_settings.cache_clear()
    await create_all_tables()
    await seed_categories()
    async with AsyncSessionLocal() as session:
        from sqlalchemy import text

        n = await session.scalar(text("select count(*) from categories"))
        print("categories=", n)
    await engine.dispose()
    print("seed_ok")


if __name__ == "__main__":
    asyncio.run(main())
