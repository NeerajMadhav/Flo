# app/channels/telegram/handlers/debt.py
"""Settlement and debt-query handlers."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from telegram import Update

from app.channels.telegram.formatters import format_settlement_preview
from app.channels.telegram.keyboards import confirm_settlement_keyboard
from app.channels.telegram.memory import remember_bot_reply
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationError
from app.nlp.schemas import ParsedMessage
from app.services.debt_service import DebtService
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import format_inr
from app.utils.guardrails import GuardrailCode, explain


async def show_confirmation(update: Update, user_id: int, parsed: ParsedMessage) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    if not (parsed.settled_person or "").strip():
        raise ValidationError(explain(GuardrailCode.SETTLEMENT_NO_PERSON))
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
    preview = format_settlement_preview(parsed)
    await msg.reply_text(preview, reply_markup=confirm_settlement_keyboard())
    await remember_bot_reply(tg_id, preview)


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
        reply = "Cancelled."
        await msg.reply_text(reply)
        await remember_bot_reply(tg_id, reply)
        return
    reply = "Type yes to confirm, or cancel."
    await msg.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def _save(update: Update, pending: dict[str, Any]) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    person = (pending.get("settled_person") or "").strip()
    if not person:
        raise ValidationError(explain(GuardrailCode.SETTLEMENT_NO_PERSON))
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
    text = f"Settlement recorded ✅\n{line}"
    await msg.reply_text(text)
    await remember_bot_reply(tg_id, text)


async def save_from_callback(update: Update, pending: dict[str, Any]) -> None:
    await _save(update, pending)


async def show_who_owes_me(update: Update, user_id: int) -> None:
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        contacts = await DebtService(session).who_owes_me(user_id)
        if not contacts:
            reply = "Nobody owes you right now. ✨"
            await update.effective_message.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return
        lines = [
            f"• {c.canonical_name}: {format_inr(c.net_balance)}" for c in contacts
        ]
    reply = "Who owes you:\n" + "\n".join(lines)
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)


async def show_i_owe(update: Update, user_id: int, name: str | None = None) -> None:
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        debts = DebtService(session)
        if name:
            c = await debts.contact_balance(user_id, name)
            reply = debts.format_balance_line(c)
            await update.effective_message.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return
        contacts = await debts.i_owe_who(user_id)
        if not contacts:
            reply = "You don't owe anyone right now. ✨"
            await update.effective_message.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return
        lines = [
            f"• {c.canonical_name}: {format_inr(abs(c.net_balance))}" for c in contacts
        ]
    reply = "You owe:\n" + "\n".join(lines)
    await update.effective_message.reply_text(reply)
    await remember_bot_reply(tg_id, reply)
