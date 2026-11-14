# tests/unit/test_settings_name.py
"""Natural name-update phrases."""

from __future__ import annotations

from app.channels.telegram.handlers.settings import extract_name_update


def test_call_me():
    assert extract_name_update("You can call me neeraj") == "Neeraj"
    assert extract_name_update("call me Neeraj") == "Neeraj"


def test_set_name():
    assert extract_name_update("set name Neeraj") == "Neeraj"


def test_reject_greeting():
    assert extract_name_update("call me hi") is None
