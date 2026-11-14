# tests/unit/test_reply_prompt.py
"""Assistant speak-layer prompt."""

from __future__ import annotations

from app.nlp.prompts import build_reply_prompt


def test_reply_prompt_is_plain_text_assistant():
    p = build_reply_prompt(
        user_context_block="Neeraj",
        recent_turns_block="user: hi",
        situation="greeting",
        user_message="hey",
        facts_block="Greet the user",
    )
    assert "Riruru" in p
    assert "PLAIN TEXT" in p
    assert "never invent" in p.lower()
    assert "hey" in p
