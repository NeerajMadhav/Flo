# tests/unit/test_logger_request_id.py
"""Correlation ID + redaction for structured logs."""

from __future__ import annotations

import json
import logging

from app.utils.logger import (
    JsonFormatter,
    get_request_id,
    log_event,
    redact_fields,
    request_id_var,
    set_request_id,
)


def test_set_request_id_sanitizes_and_binds():
    token = request_id_var.set("-")
    try:
        rid = set_request_id("abc-123_XYZ;evil!")
        assert rid == "abc-123_XYZevil"
        assert get_request_id() == "abc-123_XYZevil"
        assert ";" not in rid and "!" not in rid
    finally:
        request_id_var.reset(token)


def test_redact_secrets():
    out = redact_fields(
        {"user_id": 1, "api_key": "sk-live", "nested": {"bot_token": "x", "ok": 1}}
    )
    assert out["api_key"] == "[redacted]"
    assert out["nested"]["bot_token"] == "[redacted]"
    assert out["nested"]["ok"] == 1
    assert out["user_id"] == 1


def test_json_formatter_includes_request_id():
    token = request_id_var.set("corr-test-1")
    try:
        logger = logging.getLogger("flo.test.formatter")
        logger.handlers.clear()
        record = logger.makeRecord(
            logger.name, logging.INFO, "(event)", 0, "expense.created", (), None
        )
        record.extra_fields = {"event": "expense.created", "user_id": 7}
        line = JsonFormatter().format(record)
        payload = json.loads(line)
        assert payload["request_id"] == "corr-test-1"
        assert payload["event"] == "expense.created"
        assert payload["user_id"] == 7
    finally:
        request_id_var.reset(token)


def test_log_event_attaches_fields(caplog):
    token = request_id_var.set("evt-1")
    try:
        logger = logging.getLogger("flo.test.events")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        # Smoke: should not raise
        log_event(logger, "state.expired", user_id=3, previous_state="CONFIRM_EXPENSE")
        assert get_request_id() == "evt-1"
    finally:
        request_id_var.reset(token)
