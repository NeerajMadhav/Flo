# tests/unit/test_text_utils_intent.py
"""Soft conversational affirm/deny/skip matchers."""

from __future__ import annotations

from app.utils.text_utils import is_affirm, is_deny, is_edit_intent, is_skip


def test_affirm_variants():
    for s in ("yes", "haan", "sure", "ok", "thik hai", "go ahead"):
        assert is_affirm(s), s
    assert not is_affirm("add petrol 578")


def test_deny_variants():
    for s in ("no", "nahi", "cancel", "nope"):
        assert is_deny(s), s


def test_edit_and_skip():
    assert is_edit_intent("change")
    assert is_edit_intent("galat")
    assert is_skip("skip")
    assert is_skip("later")
    assert is_skip("baad mein")
