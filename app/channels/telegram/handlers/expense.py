# app/channels/telegram/handlers/expense.py
"""Personal expense confirm / edit / clarify handlers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from telegram import Update

from app.channels.telegram.formatters import format_expense_preview
from app.channels.telegram.keyboards import confirm_expense_keyboard, edit_field_keyboard
from app.core.database import AsyncSessionLocal
from app.nlp.schemas import ParsedMessage
from app.nlp.validate import validate_parsed_for_write
from app.services.expense_service import ExpenseService
from app.services.nlp_service import NLPService
from app.services.state_service import StateService
from app.services.user_service import UserService


def _pending_from_parsed(parsed: ParsedMessage) -> dict[str, Any]:
    return {
        "type": "expense",
        "amount": str(parsed.amount) if parsed.amount is not None else None,
        "description": parsed.description,
        "category": parsed.category,
        "date": parsed.date,
        "quantity": str(parsed.amount and parsed.amount) if False else None,
        "upi_ref": parsed.upi_ref,
        "raw_message": None,
    }


async def show_confirmation(update: Update, user_id: int, parsed: ParsedMessage, raw: str) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    validate_parsed_for_write(parsed)
    pending = _pending_from_parsed(parsed)
    pending["raw_message"] = raw
    async with AsyncSessionLocal() as session:
        await StateService(session).set_state(
            tg_id, "CONFIRM_EXPENSE", user_id=user_id, pending_data=pending
        )
    await msg.reply_text(
        format_expense_preview(parsed), reply_markup=confirm_expense_keyboard()
    )


async def handle_confirm(update: Update, state) -> None:
    msg = update.effective_message
    text = (msg.text or "").strip().lower()
    tg_id = str(update.effective_user.id)

    if text in ("yes", "y", "save", "ok", "✅"):
        await _save(update, state.pending_data or {})
        return
    if text in ("no", "cancel", "n", "❌"):
        async with AsyncSessionLocal() as session:
            await StateService(session).go_idle(tg_id)
        await msg.reply_text("Cancelled. Nothing saved.")
        return
    if text in ("edit", "change"):
        async with AsyncSessionLocal() as session:
            await StateService(session).set_state(
                tg_id,
                "EDIT_FIELD_SELECT",
                user_id=state.user_id,
                pending_data=state.pending_data,
            )
        await msg.reply_text("What do you want to change?", reply_markup=edit_field_keyboard())
        return

    # Treat as free-text edit
    async with AsyncSessionLocal() as session:
        nlp = NLPService(session)
        parsed = await nlp.parse_edit(state.user_id, state.pending_data or {}, msg.text or "")
        pending = _pending_from_parsed(parsed)
        pending["raw_message"] = (state.pending_data or {}).get("raw_message")
        await StateService(session).set_state(
            tg_id, "CONFIRM_EXPENSE", user_id=state.user_id, pending_data=pending
        )
    await msg.reply_text(
        format_expense_preview(parsed), reply_markup=confirm_expense_keyboard()
    )


async def handle_field_select(update: Update, state) -> None:
    await update.effective_message.reply_text(
        "Tap a field button, or type the change (e.g. 'amount 350').",
        reply_markup=edit_field_keyboard(),
    )


async def handle_field_value(update: Update, state) -> None:
    await handle_confirm(update, state)


async def handle_clarification(update: Update, state) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    step = state.step_data or {}
    async with AsyncSessionLocal() as session:
        nlp = NLPService(session)
        parsed = await nlp.parse_clarify(
            state.user_id,
            step.get("original_message", ""),
            step.get("clarification_question", ""),
            msg.text or "",
        )
        if parsed.needs_clarification:
            step["clarification_question"] = parsed.clarification_question
            await StateService(session).set_state(
                tg_id,
                "CLARIFYING",
                user_id=state.user_id,
                pending_data=state.pending_data,
                step_data=step,
            )
            await msg.reply_text(parsed.clarification_question or "Can you clarify?")
            return
        if parsed.type == "expense":
            await show_confirmation(update, state.user_id, parsed, step.get("original_message", ""))
        elif parsed.type == "split":
            from app.channels.telegram.handlers import split as split_handler

            await split_handler.show_confirmation(
                update, state.user_id, parsed, step.get("original_message", "")
            )
        elif parsed.type == "settlement":
            from app.channels.telegram.handlers import debt as debt_handler

            await debt_handler.show_confirmation(update, state.user_id, parsed)
        else:
            await StateService(session).go_idle(tg_id)
            await msg.reply_text("Got it — starting fresh. What would you like to log?")


async def _save(update: Update, pending: dict[str, Any]) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    async with AsyncSessionLocal() as session:
        user = await UserService(session).get_profile(tg_id)
        amount = Decimal(str(pending["amount"]))
        d = pending.get("date")
        expense_date = date.fromisoformat(d) if d else None
        expense = await ExpenseService(session).create(
            user.id,
            amount=amount,
            description=pending.get("description"),
            category_slug=pending.get("category"),
            expense_date=expense_date,
            upi_ref=pending.get("upi_ref"),
            raw_message=pending.get("raw_message"),
        )
        await StateService(session).go_idle(tg_id)
        from app.services.alert_service import AlertService

        alert = await AlertService(session).check_budget(user.id)
    text = f"Saved ✅ {expense.description or 'Expense'} — {expense.amount}"
    if alert:
        text += f"\n\n{alert}"
    await msg.reply_text(text)


async def save_from_callback(update: Update, pending: dict[str, Any]) -> None:
    await _save(update, pending)
