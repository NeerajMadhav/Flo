# app/channels/telegram/handlers/settings.py
"""Settings command and SETTINGS_* state handlers."""

from __future__ import annotations

from telegram import Update

from app.core.database import AsyncSessionLocal
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import format_inr, parse_indian_amount


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
    """SETTINGS_* free-text updates."""
    text = (update.effective_message.text or "").strip().lower()
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
            await update.effective_message.reply_text(f"Income updated to {format_inr(amt)}")
            return
        if text.startswith("set budget"):
            amt = parse_indian_amount(text.replace("set budget", "").strip())
            if amt is None:
                await update.effective_message.reply_text("Send: set budget 20000")
                return
            await users.update_profile(user, monthly_budget=amt)
            await StateService(session).go_idle(tg_id)
            await update.effective_message.reply_text(f"Budget updated to {format_inr(amt)}")
            return
        if text.startswith("set name"):
            name = update.effective_message.text.split(maxsplit=2)[-1].strip()
            await users.update_profile(user, name=name)
            await StateService(session).go_idle(tg_id)
            await update.effective_message.reply_text(f"Name updated to {name}")
            return
    await show_settings(update)
