# app/channels/telegram/handlers/settings.py
"""Settings command and SETTINGS_* state handlers."""

from __future__ import annotations

import re

from telegram import Update

from app.channels.telegram.memory import remember_bot_reply
from app.core.database import AsyncSessionLocal
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import format_inr, parse_indian_amount
from app.utils.sanitizer import sanitize_display_name

_CALL_ME = re.compile(
    r"call\s+me\s+(.+)$|"
    r"(?:set\s+)?(?:my\s+)?name\s+(?:is\s+|to\s+)?(.+)$|"
    r"^i(?:'m| am)\s+([A-Za-z][A-Za-z\s'.-]{1,40})$",
    re.IGNORECASE,
)


def extract_name_update(text: str) -> str | None:
    """Parse natural 'call me X' / 'set name X' / 'I'm X' into a display name."""
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower.startswith("set name"):
        return sanitize_display_name(raw.split(maxsplit=2)[-1]) or None
    m = _CALL_ME.search(raw)
    if not m:
        return None
    candidate = next((g for g in m.groups() if g), None)
    if not candidate:
        return None
    name = sanitize_display_name(candidate)
    if not name or len(name) < 2:
        return None
    if name.lower() in {"hi", "hey", "hello", "ok", "okay"}:
        return None
    # Title-case single/multi word names for display
    return " ".join(w.capitalize() for w in name.split())[:64]


async def show_settings(update: Update) -> None:
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        user = await UserService(session).get_profile(tg_id)
    income = format_inr(user.monthly_income) if user.is_income_set else "not set"
    budget = format_inr(user.monthly_budget) if user.is_budget_set else "not set"
    await update.effective_message.reply_text(
        f"⚙️ Settings\nName: {user.name}\nIncome: {income}\nBudget: {budget}\n\n"
        "To update, send:\n• set income 35000\n• set budget 20000\n• set name Arjun"
    )


async def handle(update: Update, state) -> None:
    """SETTINGS_* free-text updates + natural name phrases."""
    raw = update.effective_message.text or ""
    text = raw.strip().lower()
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        users = UserService(session)
        user = await users.get_profile(tg_id)
        if text.startswith("set income"):
            amt = parse_indian_amount(text.replace("set income", "").strip())
            if amt is None:
                await update.effective_message.reply_text("Send: set income 35000")
                return
            await users.update_profile(user, monthly_income=amt)
            await StateService(session).go_idle(tg_id)
            reply = f"✅ Income updated to {format_inr(amt)}"
            await update.effective_message.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return
        if text.startswith("set budget"):
            amt = parse_indian_amount(text.replace("set budget", "").strip())
            if amt is None:
                await update.effective_message.reply_text("Send: set budget 20000")
                return
            await users.update_profile(user, monthly_budget=amt)
            await StateService(session).go_idle(tg_id)
            reply = f"✅ Budget updated to {format_inr(amt)}"
            await update.effective_message.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return
        name = extract_name_update(raw)
        if name:
            await users.update_profile(user, name=name)
            await StateService(session).go_idle(tg_id)
            reply = f"✅ Got it — I'll call you {name}."
            await update.effective_message.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return
    await show_settings(update)
