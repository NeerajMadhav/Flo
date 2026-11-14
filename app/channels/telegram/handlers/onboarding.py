# app/channels/telegram/handlers/onboarding.py
"""New-user onboarding flow — short structured steps, flexible answers."""

from __future__ import annotations

import re
from decimal import Decimal

from telegram import Update

from app.core.database import AsyncSessionLocal
from app.services.state_service import StateService
from app.services.user_service import UserService
from app.utils.currency import parse_indian_amount
from app.utils.sanitizer import sanitize_display_name
from app.utils.text_utils import is_skip as _soft_skip

# Only block obvious non-names (greetings / commands), not a whitelist of names.
_NON_NAMES = frozenset(
    {
        "hi",
        "hey",
        "hello",
        "yo",
        "sup",
        "skip",
        "start",
        "help",
        "ok",
        "okay",
        "yes",
        "no",
        "cancel",
        "thanks",
        "thank you",
    }
)


def _looks_like_name(text: str) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    # "my name is X" / "I'm X" — take the trailing name-ish bit
    m = re.search(
        r"(?:my\s+name\s+is|i\s*am|i'm|this\s+is)\s+(.+)$",
        raw,
        re.IGNORECASE,
    )
    candidate = m.group(1) if m else raw
    # If they also stuffed income in the same message, cut before "and"/"income"
    candidate = re.split(
        r"\b(?:and|,)\s*(?:my\s+)?(?:income|budget|salary)\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    name = sanitize_display_name(candidate)
    if not name or len(name) < 2:
        return None
    if name.lower() in _NON_NAMES:
        return None
    # Reject pure numbers
    if re.fullmatch(r"[\d\s.,kKlL₹]+", name):
        return None
    return name[:64]


def _first_amount(text: str) -> Decimal | None:
    """Find any amount-like token in free text (30k, 30000, ₹25,000)."""
    raw = (text or "").strip()
    if not raw:
        return None
    if _soft_skip(raw):
        return None
    direct = parse_indian_amount(raw)
    if direct is not None:
        return direct
    # Standalone numeric tokens only (avoid swallowing letters from "is 30k")
    for tok in re.findall(
        r"(?<![A-Za-z])(\d[\d,]*(?:\.\d+)?\s*(?:k|l|lakh|lakhs|thousand)?)",
        raw,
        flags=re.IGNORECASE,
    ):
        amt = parse_indian_amount(tok)
        if amt is not None and amt > 0:
            return amt
    return None


def _is_skip(text: str) -> bool:
    return _soft_skip(text)


async def handle(update: Update, state_name: str) -> None:
    """Drive NEW / ONBOARD_* states with flexible, user-varied answers."""
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
                "Hey! I'm Riruru — Flo's personal finance buddy. 💰\n"
                "What should I call you?"
            )
            return

        if state_name == "ONBOARD_NAME":
            name = _looks_like_name(text)
            if not name:
                await msg.reply_text(
                    "I need a name I can use — try something like Neeraj "
                    "(not just hi/hello)."
                )
                return
            pending: dict = {"name": name}
            # Same message may also include income — accept it dynamically
            income = _first_amount(text)
            if income is not None and (
                "income" in text.lower()
                or "salary" in text.lower()
                or "earn" in text.lower()
                or re.search(r"\d", text)
                and len(text.split()) > 3
            ):
                # Only auto-take income if the message clearly isn't ONLY a name
                if any(
                    k in text.lower()
                    for k in ("income", "salary", "earn", "k", "lakh")
                ) or len(re.findall(r"\d", text)) >= 2:
                    pending["monthly_income"] = str(income)
                    await states.set_state(
                        tg_id, "ONBOARD_BUDGET", user_id=user.id, pending_data=pending
                    )
                    await msg.reply_text(
                        f"Nice to meet you, {name}! "
                        f"I'll note income around ₹{income:,.0f}.\n"
                        "What's your monthly budget? (amount or skip)"
                    )
                    return
            await states.set_state(
                tg_id, "ONBOARD_INCOME", user_id=user.id, pending_data=pending
            )
            await msg.reply_text(
                f"Nice to meet you, {name}! What's your monthly income?\n"
                "(Any amount like 30000 / 30k, or type skip)"
            )
            return

        if state_name == "ONBOARD_INCOME":
            pending = dict((await states.get_state(tg_id)).pending_data or {})
            # Allow correcting name mid-flow if they say "my name is …"
            maybe_name = _looks_like_name(text) if "name" in text.lower() else None
            if maybe_name:
                pending["name"] = maybe_name
            if _is_skip(text):
                income = None
            else:
                income = _first_amount(text)
                if income is None:
                    await msg.reply_text(
                        "Send whatever number works — 30000, 30k, or type skip."
                    )
                    return
            pending["monthly_income"] = str(income) if income is not None else None
            await states.set_state(
                tg_id, "ONBOARD_BUDGET", user_id=user.id, pending_data=pending
            )
            await msg.reply_text(
                "Got it. What's your monthly budget?\n(amount or skip)"
            )
            return

        if state_name == "ONBOARD_BUDGET":
            pending = dict((await states.get_state(tg_id)).pending_data or {})
            if _is_skip(text):
                budget = None
            else:
                budget = _first_amount(text)
                if budget is None:
                    await msg.reply_text(
                        "Send a budget amount like 20000 / 20k, or type skip."
                    )
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
                "Just talk naturally — e.g.\n"
                "• petrol 250\n• can you add lunch 600 split with Rahul\n"
                "• how much did I spend this month"
            )
            return

        await msg.reply_text("Send /start to begin.")
