# app/scheduler/jobs.py
"""APScheduler jobs — weekly/monthly reports + recurring reminders."""

from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.repositories.user_repo import UserRepository
from app.services.recurring_service import RecurringService
from app.services.report_service import ReportService
from app.utils.logger import get_logger, log_event

logger = get_logger("flo.scheduler")

# Set from main lifespan — shared Bot instance
bot = None
scheduler: AsyncIOScheduler | None = None


async def _broadcast(text_fn, label: str, sent_event: str) -> None:
    if bot is None:
        log_event(logger, "scheduler.no_bot", label=label)
        return
    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).list_active()
        for user in users:
            try:
                text = await text_fn(session, user)
                await bot.send_message(chat_id=int(user.telegram_user_id), text=text)
                log_event(
                    logger,
                    sent_event,
                    user_id=user.id,
                    telegram_user_id=user.telegram_user_id,
                )
            except Exception as e:
                log_event(
                    logger,
                    "scheduler.send_failed",
                    user_id=user.id,
                    error=str(e),
                    label=label,
                )
            await asyncio.sleep(0.05)  # stay under Telegram 30 msg/s


async def job_weekly_report() -> None:
    async def build(session, user):
        return await ReportService(session).weekly_report(user)

    await _broadcast(build, "weekly", "report.weekly.sent")


async def job_monthly_report() -> None:
    async def build(session, user):
        return await ReportService(session).monthly_report(user)

    await _broadcast(build, "monthly", "report.monthly.sent")


async def job_recurring_reminders() -> None:
    if bot is None:
        return
    try:
        async with AsyncSessionLocal() as session:
            due = await RecurringService(session).due_soon()
            users = UserRepository(session)
            for row, due_date in due:
                user = await users.get_by_id(row.user_id)
                if not user or not user.is_active:
                    continue
                try:
                    await bot.send_message(
                        chat_id=int(user.telegram_user_id),
                        text=(
                            f"⏰ Reminder: {row.description} "
                            f"({row.amount}) due on {due_date}"
                        ),
                    )
                except Exception as e:
                    log_event(logger, "scheduler.remind_failed", error=str(e))
                await asyncio.sleep(0.05)
    except Exception as e:
        log_event(logger, "scheduler.recurring_job_failed", error=str(e))


def start_scheduler(shared_bot) -> AsyncIOScheduler:
    """Start APScheduler (must run on exactly 1 Railway instance)."""
    global bot, scheduler
    bot = shared_bot
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        job_weekly_report,
        CronTrigger(
            day_of_week=settings.weekly_report_day,
            hour=settings.weekly_report_hour,
            minute=0,
            timezone=settings.timezone,
        ),
        id="weekly_report",
        replace_existing=True,
    )
    scheduler.add_job(
        job_monthly_report,
        CronTrigger(
            day=settings.monthly_report_day,
            hour=9,
            minute=0,
            timezone=settings.timezone,
        ),
        id="monthly_report",
        replace_existing=True,
    )
    scheduler.add_job(
        job_recurring_reminders,
        CronTrigger(hour=9, minute=0, timezone=settings.timezone),
        id="recurring_reminders",
        replace_existing=True,
    )
    scheduler.start()
    log_event(logger, "scheduler.started")
    return scheduler
