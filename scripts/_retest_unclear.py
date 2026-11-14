# scripts/_retest_unclear.py
"""Focused retest: unclear → clarify answer → save."""

from __future__ import annotations

import asyncio
import os
import time

os.environ.setdefault("NLP_TIMEOUT_SECONDS", "45")

from app.channels.telegram.middleware import reset_rate_limits
from app.channels.telegram.router import dispatch_text
from app.config import get_settings
from app.core.database import AsyncSessionLocal, engine
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.logger import set_request_id

TG = 900_777_001


class Msg:
    def __init__(self, text, sink):
        self.text = text
        self._sink = sink

    async def reply_text(self, text, **k):
        self._sink.append(str(text))


class Upd:
    def __init__(self, text, sink):
        self.effective_message = Msg(text, sink)
        self.effective_user = type("U", (), {"id": TG, "username": "u"})()
        self.effective_chat = type("C", (), {"type": "private"})()


async def say(text):
    reset_rate_limits()
    set_request_id()
    sink = []
    await dispatch_text(Upd(text, sink), None)
    print("USER:", text)
    for r in sink:
        print("BOT:", r[:200].replace("\n", " | "))
    return sink


async def main():
    get_settings.cache_clear()
    async with AsyncSessionLocal() as session:
        u, _ = await UserService(session).get_or_create(str(TG), "unclear")
        if not u.onboarded:
            await UserService(session).complete_onboarding(
                u, name="Unclear", monthly_income=30000, monthly_budget=10000
            )
        await StateService(session).go_idle(str(TG))
    await say("spent some money yesterday")
    await say("400 on snacks")
    r = await say("yes")
    ok = any("saved" in x.lower() or "400" in x.lower() for x in r)
    print("RESULT", "PASS" if ok else "FAIL")
    await engine.dispose()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
