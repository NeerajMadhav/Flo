# app/config.py
"""Pydantic settings loaded once from environment variables."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """
    Accept Neon/libpq URLs and make them asyncpg-ready.
    - postgresql:// → postgresql+asyncpg://
    - sslmode=require → ssl=require (asyncpg)
    - drop channel_binding (not supported by asyncpg)
    """
    raw = (url or "").strip()
    if not raw:
        return raw
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://") and not raw.startswith("postgresql+"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://") :]

    parsed = urlparse(raw)
    if not parsed.scheme.startswith("postgresql"):
        return raw

    params: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lower = key.lower()
        if lower == "channel_binding":
            continue
        if lower == "sslmode":
            # asyncpg expects ssl=require (or a SSL context), not libpq sslmode
            params.append(("ssl", value if value != "disable" else "disable"))
            continue
        if lower == "ssl":
            params.append(("ssl", value))
            continue
        params.append((key, value))

    # Neon always needs TLS; default if neither ssl nor sslmode was present
    if parsed.scheme.startswith("postgresql") and not any(k == "ssl" for k, _ in params):
        params.append(("ssl", "require"))

    return urlunparse(parsed._replace(query=urlencode(params)))


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

    # OpenRouter — free models (Nov 2026 catalog). Each role has primary + 3
    # role-specific fallbacks; nlp_global_fallback_model is the last resort for all.
    openrouter_api_key: str = Field(..., min_length=8)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # PARSE / EDIT / CLARIFY chain (JSON finance parser)
    nlp_parse_model: str = "baidu/ernie-5.5-flash-preview:free"
    nlp_parse_fallback_1: str = "google/gemma-4-31b-it:free"
    nlp_parse_fallback_2: str = "liquid/lfm-3-1.7b:free"
    nlp_parse_fallback_3: str = "inclusionai/ling-3.2-flash:free"
    # REPORT / INSIGHT chain
    nlp_report_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    nlp_report_fallback_1: str = "thinkingmachines/inkling-2-small:free"
    nlp_report_fallback_2: str = "nvidia/nemotron-3.5-super-vl:free"
    nlp_report_fallback_3: str = "baidu/ernie-5.5-flash-preview:free"
    # Global last-resort (tried after every role chain is exhausted)
    nlp_global_fallback_model: str = "openrouter/free"
    # Legacy alias — still accepted via env NLP_FALLBACK_MODEL
    nlp_fallback_model: str | None = None
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
    bot_display_name: str = "Riruru"  # user-facing persona (product = Flo)
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

    @field_validator("database_url")
    @classmethod
    def normalize_db_url(cls, v: str) -> str:
        return normalize_database_url(v)

    def dedupe_models(self, *models: str | None) -> list[str]:
        """Preserve order; drop blanks and duplicates."""
        out: list[str] = []
        seen: set[str] = set()
        for m in models:
            if not m:
                continue
            name = m.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(name)
        return out

    def parse_model_chain(self) -> list[str]:
        """PARSE/EDIT/CLARIFY: 4 role models + global fallback."""
        global_fb = self.nlp_global_fallback_model or self.nlp_fallback_model
        return self.dedupe_models(
            self.nlp_parse_model,
            self.nlp_parse_fallback_1,
            self.nlp_parse_fallback_2,
            self.nlp_parse_fallback_3,
            global_fb,
        )

    def report_model_chain(self) -> list[str]:
        """INSIGHT/report: 4 role models + global fallback."""
        global_fb = self.nlp_global_fallback_model or self.nlp_fallback_model
        return self.dedupe_models(
            self.nlp_report_model,
            self.nlp_report_fallback_1,
            self.nlp_report_fallback_2,
            self.nlp_report_fallback_3,
            global_fb,
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
