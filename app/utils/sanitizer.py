# app/utils/sanitizer.py
"""Strip prompt-injection and control characters from user-controlled text."""

from __future__ import annotations

import re

from app.config import get_settings

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"you\s+are\s+now",
    r"pretend\s+(you\s+are|to\s+be)",
    r"system\s*:",
    r"<\|.*?\|>",
    r"\[INST\]",
    r"###\s*(system|instruction)",
    r"reveal\s+((your|the)\s+)?prompt",
    r"jailbreak",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]
_NAME_SAFE = re.compile(r"[^\w\s.\-']+", re.UNICODE)


def sanitize_message(raw: str | None) -> str:
    """Return cleaned text safe to place inside <user_message> tags."""
    if not raw:
        return ""
    text = raw.strip()
    max_len = get_settings().max_message_length
    if len(text) > max_len:
        text = text[:max_len]
    text = "".join(ch for ch in text if ch >= " " or ch in "\n\t")
    for pat in _COMPILED:
        text = pat.sub("[filtered]", text)
    return text.strip()


def sanitize_display_name(raw: str | None, *, max_len: int = 64) -> str:
    """Sanitize profile / contact names before storing or injecting into prompts."""
    if not raw:
        return ""
    text = "".join(ch for ch in raw.strip() if ch >= " ")
    text = _NAME_SAFE.sub("", text)
    for pat in _COMPILED:
        text = pat.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def sanitize_for_prompt(raw: str | None, *, max_len: int = 200) -> str:
    """Encode untrusted context for LLM system/user prompt injection safety."""
    if not raw:
        return ""
    text = sanitize_message(raw)
    # Collapse newlines so attackers can't break out of a single prompt line
    text = text.replace("\n", " ").replace("\r", " ")
    return text[:max_len]


def looks_like_injection(raw: str) -> bool:
    """True if the raw message matches known injection patterns."""
    return injection_match(raw) is not None


def injection_match(raw: str) -> str | None:
    """Return the matched injection pattern string, or None if clean."""
    if not raw:
        return None
    for pat in _COMPILED:
        m = pat.search(raw)
        if m:
            return m.group(0)
    return None
