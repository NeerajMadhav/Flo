# app/core/exceptions.py
"""Domain exceptions raised by services; handlers map them to user messages."""

from __future__ import annotations


class FloBaseException(Exception):
    """Base for all Flo domain errors."""

    def __init__(self, message: str = "Something went wrong.") -> None:
        self.message = message
        super().__init__(message)


class UserNotFoundError(FloBaseException):
    def __init__(self) -> None:
        super().__init__("User not found. Send /start to begin.")


class UserNotOnboardedError(FloBaseException):
    def __init__(self) -> None:
        super().__init__("Please finish onboarding first. Send /start.")


class ValidationError(FloBaseException):
    pass


class BudgetNotSetError(FloBaseException):
    def __init__(self) -> None:
        super().__init__("No monthly budget set. Use /settings to add one.")


class IncomeNotSetError(FloBaseException):
    def __init__(self) -> None:
        super().__init__("No monthly income set. Use /settings to add one.")


class ExpenseNotFoundError(FloBaseException):
    def __init__(self) -> None:
        super().__init__("Expense not found.")


class RestoreWindowExpiredError(FloBaseException):
    def __init__(self) -> None:
        super().__init__("That expense can no longer be restored (7-day window).")


class ContactNotFoundError(FloBaseException):
    def __init__(self, name: str = "") -> None:
        super().__init__(f"No contact named '{name}'." if name else "Contact not found.")


class SplitValidationError(FloBaseException):
    pass


class GoalNotFoundError(FloBaseException):
    def __init__(self) -> None:
        super().__init__("Goal not found.")


class GoalAlreadyExistsError(FloBaseException):
    def __init__(self, name: str) -> None:
        super().__init__(f"You already have a goal named '{name}'.")


class CategoryNotFoundError(FloBaseException):
    def __init__(self, slug: str = "") -> None:
        super().__init__(f"Unknown category '{slug}'." if slug else "Category not found.")


class RateLimitExceededError(FloBaseException):
    def __init__(self) -> None:
        # Lazy import — avoids circular import at module load
        from app.utils.guardrails import GuardrailCode, explain

        super().__init__(explain(GuardrailCode.RATE_LIMIT))


class NLPParseError(FloBaseException):
    def __init__(self) -> None:
        from app.utils.guardrails import GuardrailCode, explain

        super().__init__(explain(GuardrailCode.NLP_UNAVAILABLE))


class StateExpiredError(FloBaseException):
    def __init__(self) -> None:
        from app.utils.guardrails import GuardrailCode, explain

        super().__init__(explain(GuardrailCode.STATE_EXPIRED))


class GuardrailBlockedError(FloBaseException):
    """User hit a named safety rail — message already explains which one."""

    def __init__(self, message: str, *, code: str) -> None:
        self.code = code
        super().__init__(message)
