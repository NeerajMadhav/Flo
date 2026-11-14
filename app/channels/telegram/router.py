# app/channels/telegram/router.py
"""Main text dispatcher + callback query router + webhook endpoint."""

from __future__ import annotations

import json
import logging
import secrets
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Request
from telegram import Update
from telegram.ext import ContextTypes

from app.channels.telegram.formatters import format_error
from app.channels.telegram.handlers import (
    debt,
    expense,
    fallback,
    goals,
    onboarding,
    queries,
    settings as settings_handler,
    split,
)
from app.channels.telegram.memory import remember_bot_reply
from app.channels.telegram.middleware import check_rate_limit
from app.config import get_settings
from app.core.concurrency import user_request_lock
from app.core.database import AsyncSessionLocal
from app.core.exceptions import FloBaseException, RateLimitExceededError, StateExpiredError
from app.nlp.heuristics import try_heuristic_parse
from app.nlp.validate import validate_parsed_for_write
from app.services.audit_service import AuditService
from app.services.category_service import CategoryService
from app.services.nlp_service import NLPService
from app.services.recurring_service import RecurringService
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.guardrails import GuardrailCode, check_topic_scope, explain
from app.utils.idempotency import update_id_cache
from app.utils.logger import get_logger, get_request_id, log_event, set_request_id
from app.utils.sanitizer import injection_match, sanitize_message

logger = get_logger("flo.telegram")
webhook_router = APIRouter()

# Shared PTB application — set by application.build_application / main lifespan
ptb_application = None


async def _audit_security(event: str, *, tg_id: str, **extra) -> None:
    """Persist security events that fire before the main user session."""
    async with AsyncSessionLocal() as session:
        await AuditService(session).record(
            event,
            source="telegram",
            level=logging.WARNING,
            new_value={"telegram_user_id": tg_id, **extra},
        )
        await session.commit()


async def dispatch_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MessageHandler entry for text messages."""
    # Polling path has no HTTP middleware — ensure every message has a request_id
    if get_request_id() in ("-", ""):
        set_request_id()

    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        await msg.reply_text(explain(GuardrailCode.PRIVATE_CHAT_ONLY))
        return

    tg_id = str(user.id)
    try:
        await check_rate_limit(tg_id)
    except RateLimitExceededError as e:
        await _audit_security(
            "rate_limit.exceeded", tg_id=tg_id, guardrail=GuardrailCode.RATE_LIMIT.value
        )
        await msg.reply_text(e.message)
        return

    raw = msg.text or ""
    if len(raw) > get_settings().max_message_length:
        await msg.reply_text(explain(GuardrailCode.MESSAGE_TOO_LONG))
        return
    matched = injection_match(raw)
    if matched:
        await _audit_security(
            "injection.detected",
            tg_id=tg_id,
            guardrail=GuardrailCode.INJECTION.value,
            pattern=matched[:80],
        )
        await msg.reply_text(explain(GuardrailCode.INJECTION))
        return

    # Topical / finance-scope rail (before NLP) — investment advice, off-topic, PII, crisis
    scope_hit = check_topic_scope(raw)
    if scope_hit is not None:
        event = (
            "crisis.detected"
            if scope_hit == GuardrailCode.CRISIS
            else "scope.blocked"
        )
        await _audit_security(
            event,
            tg_id=tg_id,
            guardrail=scope_hit.value,
        )
        await msg.reply_text(explain(scope_hit))
        return

    text = sanitize_message(raw)
    if not text:
        await msg.reply_text(explain(GuardrailCode.EMPTY_MESSAGE))
        return

    # Serialize per-user so state machine never interleaves under concurrent load
    async with user_request_lock(tg_id):
        try:
            async with AsyncSessionLocal() as session:
                users = UserService(session)
                db_user, _ = await users.get_or_create(tg_id, user.username)
                states = StateService(session)
                state = await states.get_state(tg_id)
                if states.last_expired:
                    await msg.reply_text(StateExpiredError().message)
                await states.append_turn(tg_id, "user", text)

                if not db_user.onboarded or state.state.startswith("ONBOARD") or state.state == "NEW":
                    await onboarding.handle(update, state.state if state.state != "IDLE" else "NEW")
                    return

                name = state.state
                if name == "CONFIRM_EXPENSE":
                    await expense.handle_confirm(update, state)
                elif name == "EDIT_FIELD_SELECT":
                    await expense.handle_field_select(update, state)
                elif name == "EDIT_FIELD_VALUE":
                    await expense.handle_field_value(update, state)
                elif name == "CONFIRM_SPLIT":
                    await split.handle_confirm(update, state)
                elif name == "EDIT_SPLIT_WHAT":
                    await split.handle_edit_what(update, state)
                elif name == "EDIT_SPLIT_VALUE":
                    await split.handle_edit_value(update, state)
                elif name == "CONFIRM_SETTLEMENT":
                    await debt.handle_confirm(update, state)
                elif name == "CLARIFYING":
                    await expense.handle_clarification(update, state)
                elif name.startswith("GOAL_"):
                    await goals.handle_state(update, state)
                elif name.startswith("SETTINGS_"):
                    await settings_handler.handle(update, state)
                elif name == "IDLE":
                    lower = text.lower()
                    if lower.startswith(("set income", "set budget", "set name")):
                        await settings_handler.handle(update, state)
                    else:
                        await _idle_nlp(update, db_user.id, tg_id, text)
                else:
                    await _idle_nlp(update, db_user.id, tg_id, text)
        except FloBaseException as e:
            await msg.reply_text(format_error(e))
        except Exception as e:
            log_event(logger, "dispatch.error", error=str(e), tg_id=tg_id)
            await msg.reply_text("Something went wrong. Try again.")


async def _idle_nlp(update: Update, user_id: int, tg_id: str, text: str) -> None:
    # Clear common phrases → skip OpenRouter (faster + survives free-tier 429s)
    parsed = try_heuristic_parse(text)
    # "same again" → re-parse last user expense/split line from conversation memory
    if parsed is None and text.strip().lower() in (
        "same",
        "same again",
        "again",
        "same thing",
        "one more",
    ):
        async with AsyncSessionLocal() as session:
            ctx = await StateService(session).get_recent_context(tg_id)
        for line in reversed(ctx.splitlines()):
            if line.startswith("user:"):
                prior = line[5:].strip()
                if prior.lower() not in (
                    "same",
                    "same again",
                    "again",
                    "yes",
                    "y",
                    "ok",
                ):
                    parsed = try_heuristic_parse(prior)
                    if parsed is not None:
                        break
    async with AsyncSessionLocal() as session:
        if parsed is None:
            nlp = NLPService(session)
            try:
                parsed = await nlp.parse(user_id, tg_id, text)
            except FloBaseException as e:
                await update.effective_message.reply_text(format_error(e))
                return
        else:
            log_event(
                logger,
                "nlp.heuristic_hit",
                parse_type=parsed.type,
                confidence=parsed.confidence,
                tg_id=tg_id,
            )

        if parsed.type == "settlement" and not (parsed.settled_person or "").strip():
            parsed.needs_clarification = True
            parsed.clarification_question = explain(GuardrailCode.SETTLEMENT_NO_PERSON)

        if parsed.needs_clarification:
            step = {
                "original_message": text,
                "clarification_question": parsed.clarification_question,
            }
            await StateService(session).set_state(
                tg_id, "CLARIFYING", user_id=user_id, step_data=step
            )
            reply = parsed.clarification_question or "Can you clarify?"
            await update.effective_message.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
            return

        if parsed.type == "expense":
            await expense.show_confirmation(update, user_id, parsed, text)
        elif parsed.type == "split":
            await split.show_confirmation(update, user_id, parsed, text)
        elif parsed.type == "settlement":
            await debt.show_confirmation(update, user_id, parsed)
        elif parsed.type == "query":
            await queries.handle(update, user_id, parsed)
        elif parsed.type == "goal":
            await goals.handle(update, user_id, parsed)
        elif parsed.type == "recurring":
            validate_parsed_for_write(parsed)
            freq = (parsed.recurrence or {}).get("frequency", "monthly")
            day = (parsed.recurrence or {}).get("day")
            row = await RecurringService(session).create(
                user_id,
                description=parsed.description or "Recurring",
                amount=Decimal(str(parsed.amount)),
                category_slug=parsed.category,
                frequency=freq,
                due_day=day,
            )
            reply = f"Recurring saved ✅ {RecurringService(session).format_line(row)}"
            await update.effective_message.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
        elif parsed.type == "greeting":
            user = await UserService(session).users.get_by_id(user_id)
            await fallback.handle_greeting(update, user.name if user else None)
        elif parsed.type == "correction":
            keyword = (parsed.description or "").strip()
            category = (parsed.category or "").strip()
            if not keyword or not category:
                reply = "Tell me like: that medicine was groceries"
                await update.effective_message.reply_text(reply)
                await remember_bot_reply(tg_id, reply)
                return
            await CategoryService(session).record_correction(
                user_id, keyword[:128], category
            )
            reply = f"Got it — I'll remember '{keyword}' as {category}."
            await update.effective_message.reply_text(reply)
            await remember_bot_reply(tg_id, reply)
        else:
            await fallback.handle_unknown(update)


async def dispatch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """CallbackQueryHandler entry."""
    if get_request_id() in ("-", ""):
        set_request_id()
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    tg_id = str(update.effective_user.id)

    async with user_request_lock(tg_id):
        await _dispatch_callback_locked(update, query, data, tg_id)


async def _dispatch_callback_locked(update, query, data: str, tg_id: str) -> None:
    async with AsyncSessionLocal() as session:
        state = await StateService(session).get_state(tg_id)
        pending = state.pending_data or {}

    try:
        if data == "expense:confirm":
            await expense.save_from_callback(update, pending)
        elif data == "expense:cancel":
            async with AsyncSessionLocal() as session:
                await StateService(session).go_idle(tg_id)
            reply = "Cancelled. Nothing saved."
            await query.edit_message_text(reply)
            await remember_bot_reply(tg_id, reply)
        elif data == "expense:edit":
            async with AsyncSessionLocal() as session:
                await StateService(session).set_state(
                    tg_id, "EDIT_FIELD_SELECT", user_id=state.user_id, pending_data=pending
                )
            from app.channels.telegram.keyboards import edit_field_keyboard

            reply = "What do you want to change?"
            await query.edit_message_text(reply, reply_markup=edit_field_keyboard())
            await remember_bot_reply(tg_id, reply)
        elif data == "split:confirm":
            await split.save_from_callback(update, pending)
        elif data == "split:edit":
            async with AsyncSessionLocal() as session:
                await StateService(session).set_state(
                    tg_id, "EDIT_SPLIT_WHAT", user_id=state.user_id, pending_data=pending
                )
            reply = (
                "What do you want to change? Reply with: amount, people, description, or category."
            )
            await query.edit_message_text(reply)
            await remember_bot_reply(tg_id, reply)
        elif data == "split:cancel":
            async with AsyncSessionLocal() as session:
                await StateService(session).go_idle(tg_id)
            reply = "Cancelled."
            await query.edit_message_text(reply)
            await remember_bot_reply(tg_id, reply)
        elif data == "settle:confirm":
            await debt.save_from_callback(update, pending)
        elif data == "settle:cancel":
            async with AsyncSessionLocal() as session:
                await StateService(session).go_idle(tg_id)
            reply = "Cancelled."
            await query.edit_message_text(reply)
            await remember_bot_reply(tg_id, reply)
        elif data.startswith("edit:"):
            field = data.split(":", 1)[1]
            if field == "back":
                from app.channels.telegram.formatters import format_expense_preview
                from app.channels.telegram.keyboards import confirm_expense_keyboard

                async with AsyncSessionLocal() as session:
                    await StateService(session).set_state(
                        tg_id, "CONFIRM_EXPENSE", user_id=state.user_id, pending_data=pending
                    )
                preview = format_expense_preview(pending)
                await query.edit_message_text(
                    preview, reply_markup=confirm_expense_keyboard()
                )
                await remember_bot_reply(tg_id, preview)
            else:
                async with AsyncSessionLocal() as session:
                    step = dict(state.step_data or {})
                    step["edit_field"] = field
                    await StateService(session).set_state(
                        tg_id,
                        "EDIT_FIELD_VALUE",
                        user_id=state.user_id,
                        pending_data=pending,
                        step_data=step,
                    )
                reply = f"Send the new {field}:"
                await query.edit_message_text(reply)
                await remember_bot_reply(tg_id, reply)
        else:
            await query.edit_message_text("Unknown action.")
    except Exception as e:
        log_event(logger, "callback.error", error=str(e), data=data)
        try:
            await query.edit_message_text("Something went wrong. Try again.")
        except Exception:
            pass


async def dispatch_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await fallback.handle_non_text(update)


async def dispatch_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mcm = update.my_chat_member
    if not mcm:
        return
    tg_id = str(mcm.from_user.id)
    status = mcm.new_chat_member.status
    async with AsyncSessionLocal() as session:
        if status == "kicked":
            await UserService(session).set_active(tg_id, False)
            log_event(logger, "user.blocked_bot", tg_id=tg_id)
        elif status == "member":
            await UserService(session).set_active(tg_id, True)
            log_event(logger, "user.unblocked_bot", tg_id=tg_id)


@webhook_router.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    settings = get_settings()
    provided = x_telegram_bot_api_secret_token or ""
    # Constant-time compare — root cause: `!=` can leak timing on secret length/match
    if not secrets.compare_digest(provided, settings.telegram_webhook_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    if ptb_application is None:
        raise HTTPException(status_code=503, detail="Bot not ready")

    # Cap body size to reduce DoS (Telegram updates are small)
    raw_body = await request.body()
    if len(raw_body) > 256_000:
        raise HTTPException(status_code=413, detail="Payload too large")

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    update = Update.de_json(data, ptb_application.bot)
    if update is None:
        return {"ok": True}
    # Atomic under concurrent Telegram retries
    if await update_id_cache.check_and_mark(update.update_id):
        return {"ok": True}
    await ptb_application.process_update(update)
    return {"ok": True}
