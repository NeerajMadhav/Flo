# app/channels/telegram/handlers/debt.py
"""Settlement and debt-query handlers."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from telegram import Update

from app.channels.telegram.formatters import format_settlement_preview
from app.channels.telegram.keyboards import confirm_settlement_keyboard
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationError
from app.nlp.schemas import ParsedMessage
from app.services.debt_service import DebtService
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import format_inr


async def show_confirmation(update: Update, user_id: int, parsed: ParsedMessage) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    if not (parsed.settled_person or "").strip():
        raise ValidationError("Who did you settle with?")
    pending = {
        "type": "settlement",
        "settled_person": parsed.settled_person,
        "settled_amount": str(parsed.settled_amount) if parsed.settled_amount is not None else None,
        "settlement_direction": parsed.settlement_direction,
    }
    async with AsyncSessionLocal() as session:
        await StateService(session).set_state(
            tg_id, "CONFIRM_SETTLEMENT", user_id=user_id, pending_data=pending
        )
    await msg.reply_text(
        format_settlement_preview(parsed), reply_markup=confirm_settlement_keyboard()
    )


async def handle_confirm(update: Update, state) -> None:
    msg = update.effective_message
    text = (msg.text or "").strip().lower()
    tg_id = str(update.effective_user.id)
    if text in ("yes", "y", "ok", "confirm"):
        await _save(update, state.pending_data or {})
        return
    if text in ("no", "cancel", "n"):
        async with AsyncSessionLocal() as session:
            await StateService(session).go_idle(tg_id)
        await msg.reply_text("Cancelled.")
        return
    await msg.reply_text("Type yes to confirm, or cancel.")


async def _save(update: Update, pending: dict[str, Any]) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    person = (pending.get("settled_person") or "").strip()
    if not person:
        raise ValidationError("Who did you settle with?")
    async with AsyncSessionLocal() as session:
        user = await UserService(session).get_profile(tg_id)
        amt_s = pending.get("settled_amount")
        amount = Decimal(amt_s) if amt_s is not None else None
        direction = pending.get("settlement_direction") or "they_pay"
        # Normalize legacy names
        if direction in ("they_paid_me",):
            direction = "they_pay"
        if direction in ("i_paid_them",):
            direction = "i_pay"
        contact = await DebtService(session).settle(
            user.id,
            person,
            amount,
            direction,
        )
        await StateService(session).go_idle(tg_id)
        line = DebtService(session).format_balance_line(contact)
    await msg.reply_text(f"Settlement recorded ✅\n{line}")


async def save_from_callback(update: Update, pending: dict[str, Any]) -> None:
    await _save(update, pending)


async def show_who_owes_me(update: Update, user_id: int) -> None:
    async with AsyncSessionLocal() as session:
        contacts = await DebtService(session).who_owes_me(user_id)
        if not contacts:
            await update.effective_message.reply_text("Nobody owes you right now. ✨")
            return
        lines = [
            f"• {c.canonical_name}: {format_inr(c.net_balance)}" for c in contacts
        ]
    await update.effective_message.reply_text("Who owes you:\n" + "\n".join(lines))


async def show_i_owe(update: Update, user_id: int, name: str | None = None) -> None:
    async with AsyncSessionLocal() as session:
        debts = DebtService(session)
        if name:
            c = await debts.contact_balance(user_id, name)
            await update.effective_message.reply_text(debts.format_balance_line(c))
            return
        contacts = await debts.i_owe_who(user_id)
        if not contacts:
            await update.effective_message.reply_text("You don't owe anyone right now. ✨")
            return
        lines = [
            f"• {c.canonical_name}: {format_inr(abs(c.net_balance))}" for c in contacts
        ]
    await update.effective_message.reply_text("You owe:\n" + "\n".join(lines))
