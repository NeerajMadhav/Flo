# app/channels/telegram/handlers/settings.py
"""Settings command and SETTINGS_* state handlers."""

from __future__ import annotations

import re

from telegram import Update

from app.channels.telegram.replies import send as reply_send
from app.channels.telegram.turn_text import user_text
from app.core.database import AsyncSessionLocal
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import format_inr, parse_indian_amount
from app.utils.sanitizer import sanitize_display_name

# "call me X" | "save/set my name as/to/is X" | "I'm X"
_CALL_ME = re.compile(
    r"call\s+me\s+(.+)$|"
    r"(?:save|set|update|change)?\s*(?:my\s+)?name\s+(?:as|to|is)\s+(.+)$|"
    r"^i(?:'m| am)\s+([A-Za-z][A-Za-z\s'.-]{1,40})$",
    re.IGNORECASE,
)


def extract_name_update(text: str) -> str | None:
    """Parse natural 'call me X' / 'save my name as X' into a display name."""
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower.startswith("set name"):
        candidate = raw.split(maxsplit=2)[-1]
    else:
        m = _CALL_ME.search(raw)
        if not m:
            return None
        candidate = next((g for g in m.groups() if g), None)
    if not candidate:
        return None
    # Drop leftover filler words
    candidate = re.sub(
        r"^(?:as|to|is|my|name|please|pls)\s+",
        "",
        candidate.strip(),
        flags=re.IGNORECASE,
    )
    name = sanitize_display_name(candidate)
    if not name or len(name) < 2:
        return None
    if name.lower() in {"hi", "hey", "hello", "ok", "okay", "as"}:
        return None
    return " ".join(w.capitalize() for w in name.split())[:64]


async def show_settings(update: Update) -> None:
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        user = await UserService(session).get_profile(tg_id)
    income = format_inr(user.monthly_income) if user.is_income_set else "not set"
    budget = format_inr(user.monthly_budget) if user.is_budget_set else "not set"
    await reply_send(
        update,
        f"⚙️ Settings\nName: {user.name}\nIncome: {income}\nBudget: {budget}\n\n"
        "To update, send:\n• set income 35000\n• set budget 20000\n• set name Arjun",
    )


async def handle(update: Update, state) -> None:
    """SETTINGS_* free-text updates + natural name phrases."""
    raw = user_text(update)
    text = raw.strip().lower()
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        users = UserService(session)
        user = await users.get_profile(tg_id)
        if text.startswith("set income"):
            amt = parse_indian_amount(text.replace("set income", "").strip())
            if amt is None:
                await reply_send(update, "Send: set income 35000")
                return
            await users.update_profile(user, monthly_income=amt)
            await StateService(session).go_idle(tg_id)
            await reply_send(update, f"✅ Income updated to {format_inr(amt)}")
            return
        if text.startswith("set budget"):
            amt = parse_indian_amount(text.replace("set budget", "").strip())
            if amt is None:
                await reply_send(update, "Send: set budget 20000")
                return
            await users.update_profile(user, monthly_budget=amt)
            await StateService(session).go_idle(tg_id)
            await reply_send(update, f"✅ Budget updated to {format_inr(amt)}")
            return
        name = extract_name_update(raw)
        if name:
            await users.update_profile(user, name=name)
            await StateService(session).go_idle(tg_id)
            await reply_send(update, f"✅ Got it — I'll call you {name}.")
            return
    await show_settings(update)
