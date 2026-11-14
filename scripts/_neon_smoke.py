# scripts/_neon_smoke.py
"""One-shot Neon connect + create_all + select 1. Not for production use."""

from __future__ import annotations

import asyncio
import importlib

from app.config import get_settings


async def main() -> None:
    get_settings.cache_clear()
    s = get_settings()
    url = s.database_url
    assert url.startswith("postgresql+asyncpg://"), url
    assert "channel_binding" not in url
    assert "ssl=" in url
    host = url.split("@", 1)[1].split("/", 1)[0]
    print("normalized_host=", host)

    import app.core.database as db

    importlib.reload(db)
    from sqlalchemy import text

    await db.create_all_tables()
    async with db.AsyncSessionLocal() as session:
        one = await session.scalar(text("select 1"))
        tables = await session.scalar(
            text(
                "select count(*) from information_schema.tables "
                "where table_schema = 'public'"
            )
        )
        print("select_1=", one)
        print("public_tables=", tables)
    await db.engine.dispose()
    print("ok")


if __name__ == "__main__":
    asyncio.run(main())
