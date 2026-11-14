# app/channels/telegram/handlers/split.py
"""Split expense confirm / edit / save handlers."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from telegram import Update

from app.channels.telegram.formatters import format_split_preview
from app.channels.telegram.keyboards import confirm_split_keyboard
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationError
from app.nlp.schemas import ParsedMessage
from app.nlp.validate import validate_parsed_for_write
from app.services.split_service import SplitService
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import format_inr, parse_indian_amount


def _pending_from_parsed(parsed: ParsedMessage) -> dict[str, Any]:
    return {
        "type": "split",
        "amount": str(parsed.amount) if parsed.amount is not None else None,
        "description": parsed.description,
        "category": parsed.category,
        "date": parsed.date,
        "split_payer": parsed.split_payer,
        "split_type": parsed.split_type or "equal",
        "split_with": parsed.split_with,
        "split_amounts": parsed.split_amounts,
        "split_total_people": parsed.split_total_people,
        "raw_message": None,
    }


async def show_confirmation(
    update: Update, user_id: int, parsed: ParsedMessage, raw: str
) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    validate_parsed_for_write(parsed)
    pending = _pending_from_parsed(parsed)
    pending["raw_message"] = raw
    async with AsyncSessionLocal() as session:
        await StateService(session).set_state(
            tg_id, "CONFIRM_SPLIT", user_id=user_id, pending_data=pending
        )
    await msg.reply_text(format_split_preview(parsed), reply_markup=confirm_split_keyboard())


async def handle_confirm(update: Update, state) -> None:
    msg = update.effective_message
    text = (msg.text or "").strip().lower()
    tg_id = str(update.effective_user.id)
    if text in ("yes", "y", "save", "ok"):
        await _save(update, state.pending_data or {})
        return
    if text in ("no", "cancel", "n"):
        async with AsyncSessionLocal() as session:
            await StateService(session).go_idle(tg_id)
        await msg.reply_text("Cancelled.")
        return
    await msg.reply_text("Tap Save / Cancel, or type yes / cancel.")


async def handle_edit_what(update: Update, state) -> None:
    """EDIT_SPLIT_WHAT — user picks which field to change."""
    msg = update.effective_message
    text = (msg.text or "").strip().lower()
    tg_id = str(update.effective_user.id)
    field = None
    if "amount" in text or "rupee" in text or "₹" in text:
        field = "amount"
    elif "people" in text or "with" in text or "friend" in text or "person" in text:
        field = "split_with"
    elif "desc" in text or "what" in text or "for" in text:
        field = "description"
    elif "categor" in text:
        field = "category"
    if not field:
        await msg.reply_text("Say one of: amount, people, description, or category.")
        return
    async with AsyncSessionLocal() as session:
        await StateService(session).set_state(
            tg_id,
            "EDIT_SPLIT_VALUE",
            user_id=state.user_id,
            pending_data=state.pending_data,
            step_data={"edit_field": field},
        )
    await msg.reply_text(f"Send the new {field.replace('split_with', 'people')}:")


async def handle_edit_value(update: Update, state) -> None:
    """EDIT_SPLIT_VALUE — apply field update and return to confirm."""
    msg = update.effective_message
    text = (msg.text or "").strip()
    tg_id = str(update.effective_user.id)
    field = (state.step_data or {}).get("edit_field")
    pending = dict(state.pending_data or {})
    if field == "amount":
        amt = parse_indian_amount(text)
        if amt is None or amt <= 0:
            await msg.reply_text("Send a valid amount, e.g. 600 or 1.5k")
            return
        pending["amount"] = str(amt)
    elif field == "description":
        if len(text) < 1:
            await msg.reply_text("Send a short description.")
            return
        pending["description"] = text
    elif field == "category":
        pending["category"] = text.lower().replace(" ", "_")
    elif field == "split_with":
        names = [
            n.strip()
            for n in re.split(r",| and | & |/", text, flags=re.IGNORECASE)
            if n.strip()
        ]
        if not names:
            await msg.reply_text("Send names, e.g. Rahul, Priya")
            return
        pending["split_with"] = names
        pending["split_total_people"] = len(names) + 1
    else:
        await msg.reply_text("Say amount, people, description, or category first.")
        async with AsyncSessionLocal() as session:
            await StateService(session).set_state(
                tg_id,
                "EDIT_SPLIT_WHAT",
                user_id=state.user_id,
                pending_data=pending,
            )
        return

    async with AsyncSessionLocal() as session:
        await StateService(session).set_state(
            tg_id,
            "CONFIRM_SPLIT",
            user_id=state.user_id,
            pending_data=pending,
            step_data={},
        )
    await msg.reply_text(
        format_split_preview(pending), reply_markup=confirm_split_keyboard()
    )


async def _save(update: Update, pending: dict[str, Any]) -> None:
    msg = update.effective_message
    tg_id = str(update.effective_user.id)
    if not pending.get("amount"):
        raise ValidationError("Split amount is missing.")
    async with AsyncSessionLocal() as session:
        user = await UserService(session).get_profile(tg_id)
        d = pending.get("date")
        expense = await SplitService(session).create_split_expense(
            user.id,
            amount=Decimal(str(pending["amount"])),
            description=pending.get("description"),
            category_slug=pending.get("category"),
            expense_date=date.fromisoformat(d) if d else None,
            split_type=pending.get("split_type") or "equal",
            split_with=pending.get("split_with") or [],
            split_amounts=pending.get("split_amounts") or {},
            split_total_people=pending.get("split_total_people"),
            split_payer=pending.get("split_payer"),
            raw_message=pending.get("raw_message"),
        )
        await StateService(session).go_idle(tg_id)
    await msg.reply_text(
        f"Split saved ✅ {expense.description or 'Expense'} — {format_inr(expense.amount)}"
    )


async def save_from_callback(update: Update, pending: dict[str, Any]) -> None:
    await _save(update, pending)
