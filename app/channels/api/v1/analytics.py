# app/channels/api/v1/analytics.py
"""Analytics summary endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import User
from app.dependencies import require_onboarded
from app.services.analytics_service import AnalyticsService
from app.utils.date_utils import month_start, today_ist

router = APIRouter(prefix="/analytics", tags=["analytics"])


class SummaryOut(BaseModel):
    month_total: Decimal
    categories: list[dict]


@router.get("/summary", response_model=SummaryOut)
async def summary(
    user: User = Depends(require_onboarded),
    session: AsyncSession = Depends(get_db),
):
    svc = AnalyticsService(session)
    total = await svc.total(user.id, month_start(), today_ist())
    breakdown = await svc.category_breakdown(user.id, month_start(), today_ist())
    return SummaryOut(
        month_total=total,
        categories=[{"name": n, "amount": a} for n, a in breakdown],
    )
