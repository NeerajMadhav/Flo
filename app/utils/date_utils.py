# app/utils/date_utils.py
"""IST date helpers and period boundaries."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Current datetime in Asia/Kolkata."""
    return datetime.now(IST)


def today_ist() -> date:
    """Today's date in IST."""
    return now_ist().date()


def month_start(d: date | None = None) -> date:
    d = d or today_ist()
    return d.replace(day=1)


def month_end(d: date | None = None) -> date:
    d = d or today_ist()
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def week_start(d: date | None = None) -> date:
    """Monday of the current week (ISO)."""
    d = d or today_ist()
    return d - timedelta(days=d.weekday())


def clamp_due_day(year: int, month: int, due_day: int) -> date:
    """Clamp due_day to last day of month (for recurring expenses)."""
    last = month_end(date(year, month, 1)).day
    return date(year, month, min(due_day, last))


def format_display(d: date) -> str:
    """Format as '14 Nov 2026'."""
    return d.strftime("%d %b %Y")
