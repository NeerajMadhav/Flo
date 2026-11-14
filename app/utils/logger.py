# app/utils/logger.py
"""Structured JSON logging with request_id correlation (ContextVar)."""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_SECRET_KEYS = re.compile(
    r"(password|secret|token|authorization|api[_-]?key|bot_token|hash)",
    re.IGNORECASE,
)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str | None = None) -> str:
    """Set correlation id; returns the id (callers that need reset should use request_id_var)."""
    rid = (value or new_request_id())[:64]
    # Sanitize — only keep printable token chars to avoid log injection via header
    rid = "".join(c for c in rid if c.isalnum() or c in "-_")[:64] or new_request_id()
    request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    return request_id_var.get()


def redact_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Drop/redact secret-like keys before logging (OWASP / OTel guidance)."""
    out: dict[str, Any] = {}
    for k, v in fields.items():
        if _SECRET_KEYS.search(k):
            out[k] = "[redacted]"
        elif isinstance(v, dict):
            out[k] = redact_fields(v)
        else:
            out[k] = v
    return out


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line with request_id."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None) or get_request_id(),
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            payload.update(redact_fields(record.extra_fields))  # type: ignore[attr-defined]
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()  # type: ignore[attr-defined]
        return True


def get_logger(name: str = "flo") -> logging.Logger:
    """Return a configured logger (idempotent)."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    logger.addHandler(handler)
    logger.setLevel(get_settings().log_level.upper())
    logger.propagate = False
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Log a named event with structured fields + request_id."""
    record = logger.makeRecord(
        logger.name, level, "(event)", 0, event, (), None
    )
    record.extra_fields = {"event": event, **redact_fields(fields)}  # type: ignore[attr-defined]
    logger.handle(record)
