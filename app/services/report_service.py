# app/services/report_service.py
"""Weekly and monthly report assembly + insight generation."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import User
from app.services.analytics_service import AnalyticsService
from app.services.goal_service import GoalService
from app.services.nlp_service import NLPService
from app.utils.currency import format_inr
from app.utils.date_utils import format_display, month_end, month_start, today_ist, week_start


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.analytics = AnalyticsService(session)
        self.goals = GoalService(session)

    async def build_stats_block(self, user_id: int, start, end) -> str:
        breakdown = await self.analytics.category_breakdown(user_id, start, end)
        total = await self.analytics.total(user_id, start, end)
        parts = [f"{name} {format_inr(amt)}" for name, amt in breakdown[:8]]
        parts.append(f"total {format_inr(total)}")
        return " | ".join(parts) if parts else f"total {format_inr(0)}"

    async def build_goals_block(self, user_id: int) -> str:
        goals = await self.goals.list_goals(user_id)
        active = [g for g in goals if not g.is_completed]
        if not active:
            return "(no active goals)"
        return " | ".join(self.goals.format_progress(g) for g in active)

    async def weekly_report(self, user: User) -> str:
        start = week_start()
        end = today_ist()
        stats = await self.build_stats_block(user.id, start, end)
        goals = await self.build_goals_block(user.id)
        budget = format_inr(user.monthly_budget) if user.is_budget_set else "not set"
        period = f"Week of {format_display(start)}–{format_display(end)}"
        insights: list[str] = []
        try:
            insights = await NLPService(self.session).generate_insights(
                user.name or "there", budget, stats, goals, period
            )
        except Exception:
            insights = []
        lines = [f"📊 {period}", stats]
        for tip in insights[:3]:
            lines.append(f"• {tip}")
        return "\n".join(lines)

    async def monthly_report(self, user: User) -> str:
        start = month_start()
        end = month_end()
        stats = await self.build_stats_block(user.id, start, min(end, today_ist()))
        goals = await self.build_goals_block(user.id)
        budget = format_inr(user.monthly_budget) if user.is_budget_set else "not set"
        period = start.strftime("%B %Y")
        insights: list[str] = []
        try:
            insights = await NLPService(self.session).generate_insights(
                user.name or "there", budget, stats, goals, period
            )
        except Exception:
            insights = []
        lines = [f"📅 {period} report", stats]
        if user.is_income_set:
            lines.append(f"Income: {format_inr(user.monthly_income)}")
        for tip in insights[:3]:
            lines.append(f"• {tip}")
        return "\n".join(lines)
