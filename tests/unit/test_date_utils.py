# tests/unit/test_date_utils.py
"""IST date helpers and month-end clamping."""

from datetime import date

from app.utils.date_utils import (
    clamp_due_day,
    format_display,
    month_end,
    month_start,
    week_start,
)


def test_month_boundaries():
    d = date(2026, 11, 14)
    assert month_start(d) == date(2026, 11, 1)
    assert month_end(d) == date(2026, 11, 30)


def test_december_month_end():
    assert month_end(date(2026, 12, 5)) == date(2026, 12, 31)


def test_week_start_monday():
    # 14 Nov 2026 is Saturday → Monday is 9 Nov
    assert week_start(date(2026, 11, 14)) == date(2026, 11, 9)


def test_clamp_due_day_february():
    assert clamp_due_day(2026, 2, 31) == date(2026, 2, 28)
    assert clamp_due_day(2024, 2, 31) == date(2024, 2, 29)  # leap
    assert clamp_due_day(2026, 1, 15) == date(2026, 1, 15)


def test_format_display():
    assert format_display(date(2026, 11, 14)) == "14 Nov 2026"
