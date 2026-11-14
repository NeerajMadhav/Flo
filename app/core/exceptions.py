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
        super().__init__("You're sending messages too fast. Wait a few seconds.")


class NLPParseError(FloBaseException):
    def __init__(self) -> None:
        super().__init__("I couldn't understand that. Try again with an amount and description.")


class StateExpiredError(FloBaseException):
    def __init__(self) -> None:
        super().__init__("Starting fresh — what would you like to log?")
