# tests/unit/test_idempotency.py
"""Telegram update_id dedupe cache."""

from app.utils.idempotency import UpdateIdCache


def test_seen_and_mark():
    cache = UpdateIdCache(maxlen=5)
    assert cache.seen(1) is False
    cache.mark(1)
    assert cache.seen(1) is True


def test_evicts_oldest():
    cache = UpdateIdCache(maxlen=3)
    cache.mark(1)
    cache.mark(2)
    cache.mark(3)
    cache.mark(4)  # evicts 1
    assert cache.seen(1) is False
    assert cache.seen(4) is True


def test_mark_idempotent():
    cache = UpdateIdCache(maxlen=10)
    cache.mark(9)
    cache.mark(9)
    assert cache.seen(9) is True
