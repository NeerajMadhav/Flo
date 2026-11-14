# tests/unit/test_nlp_json.py
"""LLM JSON extraction — raw, fenced, and invalid."""

import pytest

from app.core.exceptions import NLPParseError
from app.nlp.schemas import ParsedMessage
from app.services.nlp_service import _extract_json


def test_raw_json():
    data = _extract_json('{"type":"expense","amount":250,"confidence":0.9}')
    assert data["type"] == "expense"
    assert ParsedMessage.model_validate(data).amount == 250


def test_markdown_fenced_json():
    raw = '```json\n{"type":"query","query_intent":"total_spent_today","confidence":0.99}\n```'
    data = _extract_json(raw)
    assert data["query_intent"] == "total_spent_today"


def test_insight_array():
    data = _extract_json('["tip one", "tip two"]')
    assert data["_array"] == ["tip one", "tip two"]


def test_garbage_raises():
    with pytest.raises(NLPParseError):
        _extract_json("not json at all")


def test_parsed_message_defaults():
    p = ParsedMessage()
    assert p.type == "unknown"
    assert p.is_split is False
    assert p.needs_clarification is False
