# tests/unit/test_nlp_model_chain.py
"""NLPService walks role chain then global fallback (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import NLPParseError
from app.services.nlp_service import NLPService


@pytest.mark.asyncio
async def test_chat_tries_each_model_then_succeeds(db_session, monkeypatch):
    svc = NLPService(db_session)
    chain = ["model-a:free", "model-b:free", "openrouter/free"]
    calls: list[str] = []

    class FakeResp:
        def __init__(self, status: int, content: str = ""):
            self.status_code = status
            self._content = content

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            mid = json["model"]
            calls.append(mid)
            if mid == "model-a:free":
                return FakeResp(429)
            if mid == "model-b:free":
                return FakeResp(500)
            return FakeResp(200, '{"type":"expense","amount":1,"confidence":0.9}')

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    # bypass concurrency semaphore
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _slot():
        yield

    monkeypatch.setattr("app.core.concurrency.nlp_slot", _slot)

    out = await svc._chat("sys", "user", chain=chain)
    assert "expense" in out
    assert calls == chain


@pytest.mark.asyncio
async def test_chat_all_fail_raises(db_session, monkeypatch):
    svc = NLPService(db_session)

    class FakeResp:
        status_code = 503

        def raise_for_status(self):
            raise RuntimeError("down")

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _slot():
        yield

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.core.concurrency.nlp_slot", _slot)

    with pytest.raises(NLPParseError):
        await svc._chat("sys", "user", chain=["a:free", "b:free"])
