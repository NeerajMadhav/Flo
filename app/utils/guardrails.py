# app/utils/guardrails.py
"""
Named safety + scope rails for Riruru (Flo).

Layers (deterministic — not LLM-only):
  1. Channel / abuse   — private chat, rate limit, length, injection
  2. Ledger integrity  — amount, date, split/settlement shape (via validate.py)
  3. Topic / scope     — expense tracking only; refuse investment & off-topic advice

Industry refs mirrored here (code, not prompt faith alone):
  - OWASP LLM: injection, sensitive info, unbounded consumption, over-reliance
  - NeMo topical rails: on-topic vs off-topic before the main model
  - Finance assistants: track/categorise/confirm; no MiFID-style investment advice
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from app.config import get_settings

# ── What Riruru IS allowed to do ─────────────────────────────────────────────
ALLOWED_SCOPE = (
    "log expenses & splits",
    "track debts / settlements",
    "budgets, goals, recurring reminders",
    "answer spend queries from YOUR ledger",
    "weekly/monthly insights from YOUR numbers",
)

# ── What she must refuse (regulated / out of product) ────────────────────────
# Deterministic patterns — LLM prompt rules alone are not enough (OWASP LLM01/06).
_ADVICE_PATTERNS = [
    r"\b(which|what)\s+(stock|share|mutual\s*fund|mf|sip|crypto|bitcoin|eth)\b",
    r"\b(buy|sell|short)\s+(stock|shares|nifty|sensex|bitcoin|crypto)\b",
    r"\bshould\s+i\s+(invest|buy\s+shares|buy\s+crypto|put\s+money\s+in)\b",
    r"\b(investment|investing)\s+(advice|tip|recommend)",
    r"\b(portfolio|day\s*trad|options\s+trad|futures\s+trad)",
    r"\b(guaranteed\s+returns?|double\s+my\s+money)\b",
    r"\btax\s+(evasion|loophole|how\s+to\s+hide)\b",
    r"\b(file\s+my\s+itr|file\s+my\s+taxes)\b",
    r"\b(which\s+insurance|best\s+insurance\s+plan)\b",
    r"\b(loan\s+approval|will\s+i\s+get\s+a\s+loan)\b",
    r"\b(credit\s+score\s+hack|increase\s+cibil\s+overnight)\b",
]

_OFF_TOPIC_PATTERNS = [
    r"\b(who\s+(should|will)\s+i\s+vote|political\s+party)\b",
    r"\b(write\s+(me\s+)?(an?\s+)?(essay|poem|code|homework))\b",
    r"\b(how\s+to\s+(make|build)\s+(a\s+)?(bomb|weapon|drug))\b",
    r"\b(dating\s+advice|pick\s+up\s+lines)\b",
]

# Crisis — static care message only (no methods). Keep pattern narrow.
_CRISIS_PATTERNS = [
    r"\b(kill\s+myself|suicide|want\s+to\s+die|end\s+my\s+life)\b",
]

# Card / account-like dumps — discourage pasting secrets into chat
_PII_PATTERNS = [
    r"\b(?:\d[ -]*?){13,19}\b",  # card-like digit runs
    r"\b(?:SBIN|HDFC|ICIC|AXIS)[A-Z0-9]{6,}\b",
]

_ADVICE_RE = [re.compile(p, re.IGNORECASE) for p in _ADVICE_PATTERNS]
_OFF_TOPIC_RE = [re.compile(p, re.IGNORECASE) for p in _OFF_TOPIC_PATTERNS]
_CRISIS_RE = [re.compile(p, re.IGNORECASE) for p in _CRISIS_PATTERNS]
_PII_RE = [re.compile(p, re.IGNORECASE) for p in _PII_PATTERNS]


class GuardrailCode(str, Enum):
    """Stable codes for logs + user-facing explanations."""

    INJECTION = "injection"
    PRIVATE_CHAT_ONLY = "private_chat_only"
    EMPTY_MESSAGE = "empty_message"
    MESSAGE_TOO_LONG = "message_too_long"
    RATE_LIMIT = "rate_limit"
    AMOUNT_MISSING = "amount_missing"
    AMOUNT_TOO_HIGH = "amount_too_high"
    AMOUNT_NOT_POSITIVE = "amount_not_positive"
    DATE_INVALID = "date_invalid"
    DATE_FUTURE = "date_future"
    DATE_TOO_OLD = "date_too_old"
    SPLIT_NO_PEOPLE = "split_no_people"
    SETTLEMENT_NO_PERSON = "settlement_no_person"
    LOW_CONFIDENCE = "low_confidence"
    NLP_UNAVAILABLE = "nlp_unavailable"
    NON_TEXT = "non_text"
    STATE_EXPIRED = "state_expired"
    # Scope / topic (finance tracker only)
    FINANCIAL_ADVICE = "financial_advice"
    OFF_TOPIC = "off_topic"
    PII_SECRET = "pii_secret"
    CRISIS = "crisis"
    UNKNOWN = "unknown"


def bot_name() -> str:
    return get_settings().bot_display_name


def check_topic_scope(raw: str) -> GuardrailCode | None:
    """
    Pre-NLP topical rail. Returns a GuardrailCode if the message is out of scope,
    else None. Does not replace injection checks — run those first.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    for pat in _CRISIS_RE:
        if pat.search(text):
            return GuardrailCode.CRISIS
    for pat in _ADVICE_RE:
        if pat.search(text):
            return GuardrailCode.FINANCIAL_ADVICE
    for pat in _OFF_TOPIC_RE:
        if pat.search(text):
            return GuardrailCode.OFF_TOPIC
    for pat in _PII_RE:
        if pat.search(text):
            return GuardrailCode.PII_SECRET
    return None


def explain(code: GuardrailCode | str, **ctx: Any) -> str:
    """
    User-facing line that names Riruru and the specific guardrail.
    Always safe to send to Telegram — no secrets, no raw attacker text.
    """
    name = bot_name()
    key = code.value if isinstance(code, GuardrailCode) else str(code)
    max_amt = ctx.get("max_amount")
    scope_line = "I only help with: " + "; ".join(ALLOWED_SCOPE) + "."
    examples = {
        GuardrailCode.INJECTION.value: (
            f"I'm {name} — I only track money, I can't follow prompt/system instructions.\n"
            f"Try a normal expense: petrol 250"
        ),
        GuardrailCode.PRIVATE_CHAT_ONLY.value: (
            f"I'm {name} and I only work in private chats — message me directly."
        ),
        GuardrailCode.EMPTY_MESSAGE.value: (
            f"I'm {name}. What would you like to log? e.g. petrol 250"
        ),
        GuardrailCode.MESSAGE_TOO_LONG.value: (
            f"I'm {name}. That message is too long — keep it under "
            f"{get_settings().max_message_length} characters."
        ),
        GuardrailCode.RATE_LIMIT.value: (
            f"Whoa, slow down — I'm {name} and you're messaging too fast. "
            f"Wait a few seconds and try again."
        ),
        GuardrailCode.AMOUNT_MISSING.value: (
            f"I'm {name}. I need an amount greater than 0 — e.g. lunch 250"
        ),
        GuardrailCode.AMOUNT_NOT_POSITIVE.value: (
            f"I'm {name}. Amount must be greater than 0."
        ),
        GuardrailCode.AMOUNT_TOO_HIGH.value: (
            f"I'm {name}. That amount is over the limit"
            + (f" (max ₹{max_amt})" if max_amt is not None else "")
            + ". Check the number and try again."
        ),
        GuardrailCode.DATE_INVALID.value: (
            f"I'm {name}. That date doesn't look valid — use YYYY-MM-DD or 'today'."
        ),
        GuardrailCode.DATE_FUTURE.value: (
            f"I'm {name}. Future dates aren't allowed (except tomorrow at most)."
        ),
        GuardrailCode.DATE_TOO_OLD.value: (
            f"I'm {name}. That date is more than a year ago — I can't log it."
        ),
        GuardrailCode.SPLIT_NO_PEOPLE.value: (
            f"I'm {name}. A split needs at least one other person — "
            f"e.g. lunch 600 split with Rahul"
        ),
        GuardrailCode.SETTLEMENT_NO_PERSON.value: (
            f"I'm {name}. Who did you settle with? e.g. Rahul paid me 200"
        ),
        GuardrailCode.LOW_CONFIDENCE.value: (
            f"I'm {name} and I'm not sure I got that right — "
            f"what was it for, and how much?"
        ),
        GuardrailCode.NLP_UNAVAILABLE.value: (
            f"I'm {name} and I'm a bit stuck 😅 Send one clear line — "
            f"like petrol 250 or fuel 578 split with Surya."
        ),
        GuardrailCode.NON_TEXT.value: (
            f"I'm {name}. I only read text for now — type your expense."
        ),
        GuardrailCode.STATE_EXPIRED.value: (
            f"I'm {name}. That step timed out — starting fresh. "
            f"What would you like to log?"
        ),
        GuardrailCode.FINANCIAL_ADVICE.value: (
            f"I'm {name} — I track your spending, I don't give investment, tax, "
            f"insurance, or loan advice (that's regulated).\n"
            f"{scope_line}\n"
            f"Try: petrol 250 · how much on food this month · who owes me"
        ),
        GuardrailCode.OFF_TOPIC.value: (
            f"I'm {name} and that's outside what I do.\n"
            f"{scope_line}\n"
            f"Try logging an expense like: lunch 250"
        ),
        GuardrailCode.PII_SECRET.value: (
            f"I'm {name}. Please don't paste card/account numbers here — "
            f"I don't need them to log expenses.\n"
            f"Describe the spend instead: rent 15000 or swiggy 340"
        ),
        GuardrailCode.CRISIS.value: (
            f"I'm {name}, and I'm here for money tracking — but if you're in crisis, "
            f"please reach out for real help now: call or text 988 (US) or your local "
            f"emergency number. You matter."
        ),
        GuardrailCode.UNKNOWN.value: (
            f"I'm {name}. I didn't catch that. Try:\n"
            f"• petrol 250\n• lunch 600 split with Rahul\n"
            f"• how much did I spend this month"
        ),
    }
    return examples.get(key, examples[GuardrailCode.UNKNOWN.value])


def intro_blurb() -> str:
    """Short identity + scope line for /start and /help."""
    name = bot_name()
    return (
        f"I'm {name} — your Flo money buddy on Telegram.\n"
        f"I help with: {'; '.join(ALLOWED_SCOPE)}.\n"
        f"I don't give investment/tax/loan advice, and I block unsafe prompts "
        f"and secret dumps (card numbers, etc.)."
    )


def scope_summary_for_prompt() -> str:
    """Inject into NLP system prompts so the model stays aligned with code rails."""
    return (
        "SCOPE: You only parse money-tracking intents "
        "(expense|split|settlement|query|goal|recurring|correction|greeting).\n"
        "If the user asks for investment tips, stock picks, tax evasion, insurance "
        "product recommendations, loans, politics, homework, or unrelated chat → "
        'type:"unknown", confidence:0.0, needs_clarification:false.\n'
        "Never invent financial advice. Numbers for queries come from the app, not you."
    )
