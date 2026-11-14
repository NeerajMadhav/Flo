# app/channels/telegram/handlers/commands.py
"""Slash-command handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.channels.telegram.handlers import onboarding, settings as settings_handler
from app.core.database import AsyncSessionLocal
from app.services.state_service import StateService
from app.services.user_service import UserService


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_message:
        return
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        users = UserService(session)
        user, is_new = await users.get_or_create(tg_id, update.effective_user.username)
        states = StateService(session)
        if user.onboarded:
            await states.go_idle(tg_id)
            summary = await users.get_welcome_back_summary(user.id)
            await update.effective_message.reply_text(
                summary + "\n\nWhat would you like to log?"
            )
            return
        await states.set_state(tg_id, "NEW", user_id=user.id)
    await onboarding.handle(update, "NEW")


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        await StateService(session).go_idle(tg_id)
    await update.effective_message.reply_text("Cancelled. Starting fresh — what would you like to log?")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Flo helps you track money on Telegram.\n\n"
        "Log: petrol 250\n"
        "Split: lunch 600 split with Rahul\n"
        "Ask: how much did I spend this month\n"
        "Debt: who owes me / I paid Rahul 200\n"
        "Commands: /start /settings /cancel /help"
    )


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await settings_handler.show_settings(update)
