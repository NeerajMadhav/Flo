# app/channels/api/v1/expenses.py
"""Expense CRUD (REST)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import User
from app.dependencies import require_onboarded
from app.services.expense_service import ExpenseService
from app.utils.date_utils import month_end, month_start

router = APIRouter(prefix="/expenses", tags=["expenses"])


class ExpenseIn(BaseModel):
    amount: Decimal = Field(gt=0)
    description: Optional[str] = None
    category: Optional[str] = None
    date: Optional[date] = None


class ExpenseOut(BaseModel):
    id: int
    amount: Decimal
    description: Optional[str]
    date: date
    is_split: bool
    is_deleted: bool

    model_config = {"from_attributes": True}


@router.post("", response_model=ExpenseOut)
async def create_expense(
    body: ExpenseIn,
    user: User = Depends(require_onboarded),
    session: AsyncSession = Depends(get_db),
):
    return await ExpenseService(session).create(
        user.id,
        amount=body.amount,
        description=body.description,
        category_slug=body.category,
        expense_date=body.date,
        source="api",
    )


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    user: User = Depends(require_onboarded),
    session: AsyncSession = Depends(get_db),
):
    rows = await ExpenseService(session).repo.list_for_period(
        user.id, month_start(), month_end()
    )
    return rows


@router.delete("/{expense_id}", response_model=ExpenseOut)
async def delete_expense(
    expense_id: int,
    user: User = Depends(require_onboarded),
    session: AsyncSession = Depends(get_db),
):
    return await ExpenseService(session).soft_delete(user.id, expense_id)
