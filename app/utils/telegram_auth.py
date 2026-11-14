# app/utils/telegram_auth.py
"""Verify Telegram Login Widget payloads (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def verify_telegram_login(
    payload: dict[str, Any],
    bot_token: str,
    *,
    max_age_seconds: int = 86400,
) -> bool:
    """
    Validate Telegram Login Widget / OAuth data.

    Root cause this prevents: trusting a bare telegram_user_id from the client.
    Spec: https://core.telegram.org/widgets/login#checking-authorization
    """
    received_hash = payload.get("hash")
    if not received_hash or not isinstance(received_hash, str):
        return False
    auth_date = payload.get("auth_date")
    try:
        auth_ts = int(auth_date)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - auth_ts) > max_age_seconds:
        return False

    check_pairs = []
    for key in sorted(payload.keys()):
        if key == "hash":
            continue
        val = payload[key]
        if val is None or val == "":
            continue
        check_pairs.append(f"{key}={val}")
    data_check_string = "\n".join(check_pairs)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    computed = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, received_hash)


def build_login_hash(payload: dict[str, Any], bot_token: str) -> str:
    """Build a valid hash for tests (mirrors Telegram algorithm)."""
    check_pairs = []
    for key in sorted(payload.keys()):
        if key == "hash":
            continue
        val = payload[key]
        if val is None or val == "":
            continue
        check_pairs.append(f"{key}={val}")
    data_check_string = "\n".join(check_pairs)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    return hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
