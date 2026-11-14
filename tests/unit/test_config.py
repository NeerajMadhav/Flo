# tests/unit/test_config.py
"""Settings validation — trailing slash strip."""

from app.config import Settings, get_settings


def test_backend_url_strips_slash():
    s = Settings(
        telegram_bot_token="1234567890:ABC",
        telegram_webhook_secret="x" * 32,
        openrouter_api_key="sk-test-key",
        api_secret_key="y" * 32,
        backend_url="https://example.com/",
    )
    assert s.backend_url == "https://example.com"


def test_get_settings_cached():
    a = get_settings()
    b = get_settings()
    assert a is b
