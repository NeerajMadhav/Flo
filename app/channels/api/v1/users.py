# app/channels/api/v1/users.py
"""Current user profile endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import User
from app.dependencies import require_onboarded
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


class UserOut(BaseModel):
    id: int
    name: str
    monthly_income: Optional[Decimal] = None
    monthly_budget: Optional[Decimal] = None
    currency: str
    onboarded: bool

    model_config = {"from_attributes": True}


class UserUpdateIn(BaseModel):
    name: Optional[str] = None
    monthly_income: Optional[Decimal] = None
    monthly_budget: Optional[Decimal] = None


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(require_onboarded)):
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UserUpdateIn,
    user: User = Depends(require_onboarded),
    session: AsyncSession = Depends(get_db),
):
    return await UserService(session).update_profile(
        user, **body.model_dump(exclude_unset=True)
    )
