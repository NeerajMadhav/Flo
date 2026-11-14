# app/utils/text_utils.py
"""Telegram-safe text helpers + soft conversational intent matchers."""

from __future__ import annotations

import re

TELEGRAM_MAX = 4096

# Soft matchers — accept common English/Hinglish shortcuts for confirm UI.
# Free-form finance intent still goes through the LLM; these only cover short replies.
_AFFIRM = re.compile(
    r"^(?:yes|y|yeah|yep|yup|ok|okay|sure|save|confirm|haan|ha+|ji|"
    r"theek(?:\s+hai)?|thik(?:\s+hai)?|sahi|done|go\s*ahead|alright|"
    r"all\s*right|✅)\s*[!.]*$",
    re.IGNORECASE,
)
_DENY = re.compile(
    r"^(?:no|n|nah|nope|cancel|stop|nahi|mat|don't|dont|never\s*mind|"
    r"nevermind|❌)\s*[!.]*$",
    re.IGNORECASE,
)
_EDIT = re.compile(
    r"^(?:edit|change|fix|update|galat|wrong|modify)\s*[!.]*$",
    re.IGNORECASE,
)
_SKIP = re.compile(
    r"^(?:skip|na|n/?a|none|pass|later|baad\s*mein|-)\s*[!.]*$",
    re.IGNORECASE,
)


def truncate_telegram(text: str, limit: int = TELEGRAM_MAX) -> str:
    """Truncate at a word boundary under Telegram's message limit."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…"


def escape_md(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    specials = r"_*[]()~`>#+-=|{}.!"
    out = []
    for ch in text:
        if ch in specials:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _short_reply(text: str, max_len: int = 40) -> str | None:
    t = (text or "").strip()
    if not t or len(t) > max_len:
        return None
    return t


def is_affirm(text: str) -> bool:
    """True for short natural yes / haan / sure replies."""
    t = _short_reply(text)
    return bool(t and _AFFIRM.match(t))


def is_deny(text: str) -> bool:
    """True for short natural no / nahi / cancel replies."""
    t = _short_reply(text)
    return bool(t and _DENY.match(t))


def is_edit_intent(text: str) -> bool:
    """True for short edit/change replies (confirm UI)."""
    t = _short_reply(text)
    return bool(t and _EDIT.match(t))


def is_skip(text: str) -> bool:
    """True for skip / later / pass style answers."""
    t = _short_reply(text, max_len=24)
    return bool(t and _SKIP.match(t))
