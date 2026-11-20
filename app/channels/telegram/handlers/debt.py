# app/channels/telegram/handlers/debt.py
"""Settlement and debt-query handlers."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from telegram import Update

from app.channels.telegram.formatters import format_settlement_preview
from app.channels.telegram.keyboards import confirm_settlement_keyboard
from app.channels.telegram.replies import send as reply_send
from app.channels.telegram.turn_text import user_text
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationError
from app.nlp.schemas import ParsedMessage
from app.services.debt_service import DebtService
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import format_inr
from app.utils.guardrails import GuardrailCode, explain
from app.utils.text_utils import is_affirm, is_deny


async def show_confirmation(update: Update, user_id: int, parsed: ParsedMessage) -> None:
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
    await reply_send(update, preview, reply_markup=confirm_settlement_keyboard())


async def handle_confirm(update: Update, state) -> None:
    raw = user_text(update)
    tg_id = str(update.effective_user.id)
    if is_affirm(raw):
        await _save(update, state.pending_data or {})
        return
    if is_deny(raw):
        async with AsyncSessionLocal() as session:
            await StateService(session).go_idle(tg_id)
        await reply_send(update, "Cancelled.")
        return
    await reply_send(update, "Say yes / haan to confirm, or cancel.")


async def _save(update: Update, pending: dict[str, Any]) -> None:
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
    await reply_send(update, f"Settlement recorded ✅\n{line}")


async def save_from_callback(update: Update, pending: dict[str, Any]) -> None:
    await _save(update, pending)


async def show_who_owes_me(update: Update, user_id: int) -> None:
    async with AsyncSessionLocal() as session:
        contacts = await DebtService(session).who_owes_me(user_id)
        if not contacts:
            await reply_send(update, "Nobody owes you right now. ✨")
            return
        lines = [
            f"• {c.canonical_name}: {format_inr(c.net_balance)}" for c in contacts
        ]
    await reply_send(update, "Who owes you:\n" + "\n".join(lines))


async def show_i_owe(update: Update, user_id: int, name: str | None = None) -> None:
    async with AsyncSessionLocal() as session:
        debts = DebtService(session)
        if name:
            c = await debts.contact_balance(user_id, name)
            await reply_send(update, debts.format_balance_line(c))
            return
        contacts = await debts.i_owe_who(user_id)
        if not contacts:
            await reply_send(update, "You don't owe anyone right now. ✨")
            return
        lines = [
            f"• {c.canonical_name}: {format_inr(abs(c.net_balance))}" for c in contacts
        ]
    await reply_send(update, "You owe:\n" + "\n".join(lines))
