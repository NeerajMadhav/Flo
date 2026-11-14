# tests/unit/test_database_url.py
"""Neon / libpq URL normalization for asyncpg."""

from __future__ import annotations

from app.config import normalize_database_url


def test_neon_url_becomes_asyncpg_and_drops_channel_binding():
    raw = (
        "postgresql://u:p@ep-x-pooler.c-16.us-east-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    out = normalize_database_url(raw)
    assert out.startswith("postgresql+asyncpg://")
    assert "channel_binding" not in out
    assert "ssl=require" in out
    assert "sslmode" not in out


def test_sqlite_unchanged():
    assert normalize_database_url("sqlite+aiosqlite:///./flo.db") == (
        "sqlite+aiosqlite:///./flo.db"
    )
