# app/channels/telegram/handlers/expense.py
"""Personal expense confirm / edit / clarify handlers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from telegram import Update

from app.channels.telegram.formatters import format_expense_preview
from app.channels.telegram.keyboards import confirm_expense_keyboard, edit_field_keyboard
from app.channels.telegram.presence import show_typing
from app.channels.telegram.replies import send as reply_send
from app.channels.telegram.turn_text import user_text
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationError
from app.nlp.heuristics import try_heuristic_parse
from app.nlp.schemas import ParsedMessage
from app.nlp.validate import validate_parsed_for_write
from app.services.expense_service import ExpenseService
from app.services.nlp_service import NLPService
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import parse_indian_amount
from app.utils.guardrails import GuardrailCode, explain
from app.utils.text_utils import is_affirm, is_deny, is_edit_intent


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
    tg_id = str(update.effective_user.id)
    validate_parsed_for_write(parsed)
    pending = _pending_from_parsed(parsed)
    pending["raw_message"] = raw
    async with AsyncSessionLocal() as session:
        await StateService(session).set_state(
            tg_id, "CONFIRM_EXPENSE", user_id=user_id, pending_data=pending
        )
    preview = format_expense_preview(parsed)
    await reply_send(update, preview, reply_markup=confirm_expense_keyboard())


async def handle_confirm(update: Update, state) -> None:
    raw_text = user_text(update)
    tg_id = str(update.effective_user.id)

    if is_affirm(raw_text):
        await _save(update, state.pending_data or {})
        return
    if is_deny(raw_text):
        async with AsyncSessionLocal() as session:
            await StateService(session).go_idle(tg_id)
        await reply_send(update, "Cancelled. Nothing saved.")
        return
    if is_edit_intent(raw_text):
        async with AsyncSessionLocal() as session:
            await StateService(session).set_state(
                tg_id,
                "EDIT_FIELD_SELECT",
                user_id=state.user_id,
                pending_data=state.pending_data,
            )
        await reply_send(
            update,
            "What do you want to change?",
            reply_markup=edit_field_keyboard(),
        )
        return

    # Deterministic amount tweak: "amount 150" / "150" / "change to 150"
    pending = dict(state.pending_data or {})
    raw_edit = raw_text
    amt_direct = None
    lower = raw_edit.lower()
    if lower.startswith("amount "):
        amt_direct = parse_indian_amount(raw_edit.split(" ", 1)[1])
    elif lower.startswith("change to "):
        amt_direct = parse_indian_amount(raw_edit.split(" ", 2)[2])
    else:
        amt_direct = parse_indian_amount(raw_edit)
    if amt_direct is not None and amt_direct > 0:
        pending["amount"] = str(amt_direct)
        async with AsyncSessionLocal() as session:
            await StateService(session).set_state(
                tg_id, "CONFIRM_EXPENSE", user_id=state.user_id, pending_data=pending
            )
        preview = format_expense_preview(pending)
        await reply_send(update, preview, reply_markup=confirm_expense_keyboard())
        return

    # Free text while confirming: maybe a brand-new ask, or an edit of pending
    async with AsyncSessionLocal() as session:
        nlp = NLPService(session)
        fresh = await nlp.parse(state.user_id, tg_id, raw_text)
        if (
            fresh.type in ("expense", "split", "settlement", "goal", "query")
            and not fresh.needs_clarification
            and float(fresh.confidence or 0) >= 0.75
        ):
            await StateService(session).go_idle(tg_id)
            await _route_resolved_parse(update, state.user_id, fresh, raw_text)
            return

        parsed = await nlp.parse_edit(
            state.user_id, state.pending_data or {}, raw_text
        )
        if parsed.needs_clarification:
            reply = parsed.clarification_question or explain(GuardrailCode.LOW_CONFIDENCE)
            await reply_send(update, reply)
            return
        try:
            validate_parsed_for_write(parsed)
        except ValidationError as e:
            await reply_send(update, e.message)
            return
        pending = _pending_from_parsed(parsed)
        pending["raw_message"] = (state.pending_data or {}).get("raw_message")
        await StateService(session).set_state(
            tg_id, "CONFIRM_EXPENSE", user_id=state.user_id, pending_data=pending
        )
    preview = format_expense_preview(parsed)
    await reply_send(update, preview, reply_markup=confirm_expense_keyboard())


async def handle_field_select(update: Update, state) -> None:
    await reply_send(
        update,
        "Tap a field button, or type the change (e.g. 'amount 350').",
        reply_markup=edit_field_keyboard(),
    )


async def handle_field_value(update: Update, state) -> None:
    """Apply the field chosen in EDIT_FIELD_SELECT (amount/category/…)."""
    tg_id = str(update.effective_user.id)
    field = (state.step_data or {}).get("edit_field") or "amount"
    raw = user_text(update)
    pending = dict(state.pending_data or {})

    # Fresh expense while editing → abandon edit and let caller re-route
    # (router checks heuristic before calling us when possible)

    # User pasted a full new log while editing → abandon edit and re-parse
    if (
        any(ch.isdigit() for ch in raw)
        and len(raw.split()) >= 2
        and field in ("category", "description", "date")
    ):
        async with AsyncSessionLocal() as session:
            await StateService(session).go_idle(tg_id)
            nlp = NLPService(session)
            try:
                fresh = await nlp.parse(state.user_id, tg_id, raw)
            except Exception:
                fresh = None
        if fresh is not None and not fresh.needs_clarification:
            await _route_resolved_parse(update, state.user_id, fresh, raw)
            return
        await reply_send(update, "Got it — starting fresh. Send the expense again?")
        return

    if field == "amount":
        amt = parse_indian_amount(raw)
        if amt is None or amt <= 0:
            await reply_send(update, "Send a valid amount, e.g. 350 or 1.5k")
            return
        pending["amount"] = str(amt)
    elif field == "category":
        if len(raw) < 2:
            await reply_send(update, "Send a category like fuel or food_outside ⛽")
            return
        pending["category"] = raw.lower().replace(" ", "_")[:64]
    elif field == "description":
        if len(raw) < 1:
            await reply_send(update, "Send a short description.")
            return
        pending["description"] = raw[:128]
    elif field == "date":
        pending["date"] = raw[:32]
    else:
        await handle_confirm(update, state)
        return

    async with AsyncSessionLocal() as session:
        await StateService(session).set_state(
            tg_id,
            "CONFIRM_EXPENSE",
            user_id=state.user_id,
            pending_data=pending,
            step_data={},
        )
    preview = format_expense_preview(pending)
    await reply_send(update, preview, reply_markup=confirm_expense_keyboard())


async def _route_resolved_parse(
    update: Update, user_id: int, parsed: ParsedMessage, original: str
) -> None:
    """Send confirm / handle after clarification resolved to a typed parse."""
    if parsed.type == "expense":
        await show_confirmation(update, user_id, parsed, original)
    elif parsed.type == "split":
        from app.channels.telegram.handlers import split as split_handler

        await split_handler.show_confirmation(update, user_id, parsed, original)
    elif parsed.type == "settlement":
        from app.channels.telegram.handlers import debt as debt_handler

        await debt_handler.show_confirmation(update, user_id, parsed)
    elif parsed.type == "goal":
        from app.channels.telegram.handlers import goals as goals_handler

        await goals_handler.handle(update, user_id, parsed)
    elif parsed.type == "query":
        from app.channels.telegram.handlers import queries as queries_handler

        await queries_handler.handle(update, user_id, parsed)
    else:
        tg_id = str(update.effective_user.id)
        async with AsyncSessionLocal() as session:
            await StateService(session).go_idle(tg_id)
        await reply_send(update, "Got it — starting fresh. What would you like to log?")


async def handle_clarification(update: Update, state) -> None:
    """Resolve CLARIFYING via NLP (any phrasing); tiny heuristic only if models fail."""
    tg_id = str(update.effective_user.id)
    step = state.step_data or {}
    answer = user_text(update)
    original = step.get("original_message", "")

    await show_typing(update)
    async with AsyncSessionLocal() as session:
        nlp = NLPService(session)
        parsed = await nlp.parse_clarify(
            state.user_id,
            original,
            step.get("clarification_question", ""),
            answer,
        )
        # If clarify failed, treat the answer as a fresh message (user may restate fully)
        if parsed.needs_clarification and float(parsed.confidence or 0) < 0.5:
            try:
                parsed = await nlp.parse(state.user_id, tg_id, answer)
            except Exception:
                pass
        if parsed.needs_clarification and float(parsed.confidence or 0) == 0.0:
            retry = try_heuristic_parse(answer)
            if retry is not None:
                parsed = retry
        if parsed.needs_clarification:
            step["clarification_question"] = parsed.clarification_question
            await StateService(session).set_state(
                tg_id,
                "CLARIFYING",
                user_id=state.user_id,
                pending_data=state.pending_data,
                step_data=step,
            )
            reply = parsed.clarification_question or "Can you clarify?"
            await reply_send(update, reply)
            return
        await StateService(session).go_idle(tg_id)

    await _route_resolved_parse(update, state.user_id, parsed, original or answer)


def _pending_amount(pending: dict[str, Any]) -> Decimal:
    """Parse pending amount safely — never Decimal('None')."""
    raw = pending.get("amount")
    if raw is None or str(raw).strip().lower() in ("", "none", "null"):
        raise ValidationError(explain(GuardrailCode.AMOUNT_MISSING))
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, ValueError) as e:
        raise ValidationError(explain(GuardrailCode.AMOUNT_MISSING)) from e
    if amount <= 0:
        raise ValidationError(explain(GuardrailCode.AMOUNT_NOT_POSITIVE))
    return amount


async def _save(update: Update, pending: dict[str, Any]) -> None:
    tg_id = str(update.effective_user.id)
    amount = _pending_amount(pending)
    async with AsyncSessionLocal() as session:
        user = await UserService(session).get_profile(tg_id)
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
    await reply_send(update, text)


async def save_from_callback(update: Update, pending: dict[str, Any]) -> None:
    await _save(update, pending)
