# tests/unit/test_rate_limit.py
"""Rate limit: per-minute + burst windows."""

import pytest

from app.channels.telegram.middleware import check_rate_limit_sync, reset_rate_limits
from app.config import get_settings
from app.core.exceptions import RateLimitExceededError


def test_allows_under_limit():
    reset_rate_limits()
    for _ in range(4):
        check_rate_limit_sync("u1")
    reset_rate_limits()


def test_burst_limit_trips():
    reset_rate_limits()
    settings = get_settings()
    original_burst = settings.rate_limit_burst_per_5s
    object.__setattr__(settings, "rate_limit_burst_per_5s", 3)
    try:
        check_rate_limit_sync("burst-user")
        check_rate_limit_sync("burst-user")
        check_rate_limit_sync("burst-user")
        with pytest.raises(RateLimitExceededError):
            check_rate_limit_sync("burst-user")
    finally:
        object.__setattr__(settings, "rate_limit_burst_per_5s", original_burst)
        reset_rate_limits()


def test_per_minute_limit_trips():
    reset_rate_limits()
    settings = get_settings()
    original = settings.rate_limit_messages_per_min
    original_burst = settings.rate_limit_burst_per_5s
    object.__setattr__(settings, "rate_limit_messages_per_min", 5)
    object.__setattr__(settings, "rate_limit_burst_per_5s", 100)
    try:
        for _ in range(5):
            check_rate_limit_sync("min-user")
        with pytest.raises(RateLimitExceededError):
            check_rate_limit_sync("min-user")
    finally:
        object.__setattr__(settings, "rate_limit_messages_per_min", original)
        object.__setattr__(settings, "rate_limit_burst_per_5s", original_burst)
        reset_rate_limits()


def test_users_isolated():
    reset_rate_limits()
    settings = get_settings()
    original_burst = settings.rate_limit_burst_per_5s
    object.__setattr__(settings, "rate_limit_burst_per_5s", 2)
    try:
        check_rate_limit_sync("a")
        check_rate_limit_sync("a")
        with pytest.raises(RateLimitExceededError):
            check_rate_limit_sync("a")
        check_rate_limit_sync("b")
    finally:
        object.__setattr__(settings, "rate_limit_burst_per_5s", original_burst)
        reset_rate_limits()
