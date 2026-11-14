# app/channels/telegram/handlers/commands.py
"""Slash-command handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.channels.telegram.handlers import onboarding, settings as settings_handler
from app.channels.telegram.memory import remember_bot_reply
from app.core.database import AsyncSessionLocal
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.guardrails import GuardrailCode, explain, intro_blurb


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_message:
        return
    tg_id = str(update.effective_user.id)
    onboarded_reply: str | None = None
    async with AsyncSessionLocal() as session:
        users = UserService(session)
        user, is_new = await users.get_or_create(tg_id, update.effective_user.username)
        states = StateService(session)
        if user.onboarded:
            await states.go_idle(tg_id)
            summary = await users.get_welcome_back_summary(user.id)
            onboarded_reply = (
                f"{intro_blurb()}\n\n{summary}\n\n"
                f"What would you like to log, {user.name or 'friend'}?"
            )
        else:
            await states.set_state(tg_id, "NEW", user_id=user.id)
    if onboarded_reply is not None:
        await update.effective_message.reply_text(onboarded_reply)
        await remember_bot_reply(tg_id, onboarded_reply)
        return
    await onboarding.handle(update, "NEW")


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        await StateService(session).go_idle(tg_id)
    reply = "Cancelled. " + explain(GuardrailCode.STATE_EXPIRED)
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_id = str(update.effective_user.id)
    reply = (
        intro_blurb()
        + "\n\n"
        "Log: petrol 250\n"
        "Split: lunch 600 split with Rahul\n"
        "Ask: how much did I spend this month\n"
        "Debt: who owes me / I paid Rahul 200\n"
        "Commands: /start /settings /cancel /help"
    )
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await settings_handler.show_settings(update)
