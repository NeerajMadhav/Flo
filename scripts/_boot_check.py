# scripts/_boot_check.py
"""Verify Telegram + OpenRouter + Neon config without starting the full bot."""

from __future__ import annotations

import asyncio
import sys

import httpx

from app.config import get_settings


async def main() -> int:
    get_settings.cache_clear()
    s = get_settings()

    ok = True
    # Telegram getMe
    async with httpx.AsyncClient(timeout=20) as client:
        tg = await client.get(f"https://api.telegram.org/bot{s.telegram_bot_token}/getMe")
        tg_data = tg.json()
        if not tg_data.get("ok"):
            print("telegram=FAIL", tg_data)
            ok = False
        else:
            u = tg_data["result"]
            print("telegram=OK", f"@{u.get('username')}", u.get("first_name"))

        # OpenRouter models ping (auth check)
        or_resp = await client.get(
            f"{s.openrouter_base_url}/models",
            headers={"Authorization": f"Bearer {s.openrouter_api_key}"},
        )
        if or_resp.status_code != 200:
            print("openrouter=FAIL", or_resp.status_code, or_resp.text[:200])
            ok = False
        else:
            print("openrouter=OK")

    # Neon
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal, engine

    async with AsyncSessionLocal() as session:
        one = await session.scalar(text("select 1"))
        cats = await session.scalar(text("select count(*) from categories"))
        print("neon=OK", f"select_1={one}", f"categories={cats}")
    await engine.dispose()

    print("bot_mode=", s.bot_mode)
    print("boot_check=", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
