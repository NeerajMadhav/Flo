# app/core/models.py
"""SQLAlchemy ORM models for Flo — all tables and relationships."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base


class User(Base):
    """Telegram-linked Flo user profile."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    monthly_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    language_pref: Mapped[str] = mapped_column(String(8), default="en")
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    expenses: Mapped[list[Expense]] = relationship(back_populates="user")
    contacts: Mapped[list[Contact]] = relationship(back_populates="user")
    goals: Mapped[list[SavingsGoal]] = relationship(back_populates="user")

    @property
    def is_budget_set(self) -> bool:
        return self.monthly_budget is not None

    @property
    def is_income_set(self) -> bool:
        return self.monthly_income is not None


class Category(Base):
    """Expense category — defaults have user_id=NULL; custom are per-user."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("slug", "user_id", name="uq_category_slug_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    icon_emoji: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecurringExpense(Base):
    """Recurring bill / subscription reminder template."""

    __tablename__ = "recurring_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    due_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_logged_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    remind_days_before: Mapped[int] = mapped_column(Integer, default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Expense(Base):
    """Logged expense. amount = total paid out (not always user share)."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_split: Mapped[bool] = mapped_column(Boolean, default=False)
    split_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurring_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recurring_expenses.id"), nullable=True)
    upi_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="telegram")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="expenses")
    category: Mapped[Optional[Category]] = relationship()
    participants: Mapped[list[SplitParticipant]] = relationship(
        back_populates="expense", cascade="all, delete-orphan"
    )


class SplitParticipant(Base):
    """One person's share of a split expense (bidirectional debt)."""

    __tablename__ = "split_participants"
    __table_args__ = (
        CheckConstraint("direction IN ('they_owe_me', 'i_owe_them')", name="ck_split_direction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_name: Mapped[str] = mapped_column(String(128), nullable=False)
    split_type: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_share: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    amount_owed: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    user_share: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="they_owe_me")
    is_settled: Mapped[bool] = mapped_column(Boolean, default=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    expense: Mapped[Expense] = relationship(back_populates="participants")


class Contact(Base):
    """Person the user splits with. net_balance > 0 means they owe the user."""

    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("user_id", "canonical_name", name="uq_contact_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    aliases: Mapped[list[Any]] = mapped_column(JSON, default=list)
    telegram_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    net_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="contacts")


class ConversationState(Base):
    """Per-Telegram-user conversation state machine row."""

    __tablename__ = "conversation_state"

    telegram_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="IDLE")
    pending_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    step_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SavingsGoal(Base):
    """Named savings goal with running balance."""

    __tablename__ = "savings_goals"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_goal_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="goals")


class BudgetAlert(Base):
    """Budget threshold alert (overall or per-category)."""

    __tablename__ = "budget_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    threshold_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    threshold_type: Mapped[str] = mapped_column(String(16), default="absolute")
    period: Mapped[str] = mapped_column(String(16), default="monthly")
    alert_at_percent: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RateLimit(Base):
    """Per-user rate-limit window counters."""

    __tablename__ = "rate_limits"

    telegram_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    burst_count: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    """Append-only audit trail for sensitive actions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    old_value: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserCategoryCorrection(Base):
    """User-taught keyword → category mapping for NLP few-shot injection."""

    __tablename__ = "user_category_corrections"
    __table_args__ = (UniqueConstraint("user_id", "keyword", name="uq_correction_user_keyword"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(128), nullable=False)
    correct_category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship()
