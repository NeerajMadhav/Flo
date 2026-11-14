# tests/unit/test_telegram_auth.py
"""Telegram Login Widget HMAC verification."""

import time

from app.utils.telegram_auth import build_login_hash, verify_telegram_login

BOT = "123456:ABC-TESTTOKEN"


def test_valid_login_hash():
    payload = {
        "id": 1001,
        "first_name": "Arjun",
        "username": "arjun",
        "auth_date": int(time.time()),
    }
    payload["hash"] = build_login_hash(payload, BOT)
    assert verify_telegram_login(payload, BOT) is True


def test_tampered_id_fails():
    payload = {
        "id": 1001,
        "first_name": "Arjun",
        "auth_date": int(time.time()),
    }
    payload["hash"] = build_login_hash(payload, BOT)
    payload["id"] = 9999  # spoof
    assert verify_telegram_login(payload, BOT) is False


def test_expired_auth_date_fails():
    payload = {
        "id": 1001,
        "first_name": "Arjun",
        "auth_date": int(time.time()) - 100_000,
    }
    payload["hash"] = build_login_hash(payload, BOT)
    assert verify_telegram_login(payload, BOT, max_age_seconds=86400) is False


def test_missing_hash_fails():
    assert verify_telegram_login({"id": 1, "auth_date": int(time.time())}, BOT) is False
