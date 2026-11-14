# app/config.py
"""Pydantic settings loaded once from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration. Missing required secrets fail startup."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str = Field(..., min_length=10)
    telegram_webhook_secret: str = Field(..., min_length=32)
    backend_url: str = "http://localhost:8000"
    bot_mode: str = "polling"  # polling | webhook

    # Database
    database_url: str = "sqlite+aiosqlite:///./flo.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # OpenRouter
    openrouter_api_key: str = Field(..., min_length=8)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    nlp_parse_model: str = "google/gemini-2.0-flash-exp:free"
    nlp_report_model: str = "anthropic/claude-3-haiku"
    nlp_fallback_model: str = "meta-llama/llama-3.1-8b-instruct:free"
    nlp_max_tokens: int = 500
    nlp_temperature: float = 0.1
    nlp_timeout_seconds: int = 10
    nlp_max_retries: int = 1
    nlp_max_concurrent: int = 8  # max parallel OpenRouter calls process-wide

    # JWT
    api_secret_key: str = Field(..., min_length=32)
    jwt_expire_hours: int = 168  # 7 days — shorter than prior 30d MVP default

    # App
    timezone: str = "Asia/Kolkata"
    debug: bool = False  # MUST stay false in production (SQL echo leaks PII)
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    webhook_rate_limit_per_min: int = 120

    # Scheduler
    weekly_report_day: int = 6
    weekly_report_hour: int = 20
    monthly_report_day: int = 1

    # Limits
    rate_limit_messages_per_min: int = 20
    rate_limit_burst_per_5s: int = 5
    rate_limit_api_per_min: int = 60
    max_amount_per_transaction: float = 1_000_000
    max_message_length: int = 4096
    state_expiry_minutes: int = 30
    railway_max_instances: int = 1

    @field_validator("backend_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
