# app/utils/text_utils.py
"""Telegram-safe text helpers."""

from __future__ import annotations

TELEGRAM_MAX = 4096


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
