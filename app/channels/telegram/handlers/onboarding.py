# app/channels/telegram/handlers/onboarding.py
"""New-user onboarding flow."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import ContextTypes

from app.core.database import AsyncSessionLocal
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import parse_indian_amount


async def handle(update: Update, state_name: str) -> None:
    """Drive NEW / ONBOARD_* states."""
    msg = update.effective_message
    if not msg or not update.effective_user:
        return
    text = (msg.text or "").strip()
    tg_id = str(update.effective_user.id)

    async with AsyncSessionLocal() as session:
        users = UserService(session)
        states = StateService(session)
        user, _ = await users.get_or_create(tg_id, update.effective_user.username)

        if state_name in ("NEW", "IDLE") and not user.onboarded:
            await states.set_state(tg_id, "ONBOARD_NAME", user_id=user.id)
            await msg.reply_text(
                "Hey! I'm Riruru — Flo's personal finance buddy. 💰\nWhat's your name?"
            )
            return

        if state_name == "ONBOARD_NAME":
            if len(text) < 2:
                await msg.reply_text("Please send your name (at least 2 characters).")
                return
            await states.set_state(
                tg_id, "ONBOARD_INCOME", user_id=user.id, pending_data={"name": text}
            )
            await msg.reply_text(
                f"Nice to meet you, {text}! What's your monthly income?\n"
                "(Send an amount like 30000, or type skip)"
            )
            return

        if state_name == "ONBOARD_INCOME":
            pending = (await states.get_state(tg_id)).pending_data or {}
            income = None
            if text.lower() != "skip":
                income = parse_indian_amount(text)
                if income is None:
                    await msg.reply_text("Send a number like 30000, or type skip.")
                    return
            pending["monthly_income"] = str(income) if income is not None else None
            await states.set_state(
                tg_id, "ONBOARD_BUDGET", user_id=user.id, pending_data=pending
            )
            await msg.reply_text(
                "Got it. What's your monthly budget?\n(Send an amount, or type skip)"
            )
            return

        if state_name == "ONBOARD_BUDGET":
            pending = (await states.get_state(tg_id)).pending_data or {}
            budget = None
            if text.lower() != "skip":
                budget = parse_indian_amount(text)
                if budget is None:
                    await msg.reply_text("Send a number like 20000, or type skip.")
                    return
            name = pending.get("name") or "Friend"
            income_s = pending.get("monthly_income")
            income = Decimal(income_s) if income_s else None
            await users.complete_onboarding(
                user,
                name=name,
                monthly_income=income,
                monthly_budget=budget,
            )
            await states.go_idle(tg_id)
            await msg.reply_text(
                f"You're all set, {name}! ✅\n\n"
                "Try logging an expense:\n• petrol 250\n• lunch 600 split with Rahul\n"
                "• how much did I spend today"
            )
            return

        await msg.reply_text("Send /start to begin.")
