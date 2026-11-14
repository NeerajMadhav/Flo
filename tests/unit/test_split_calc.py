# tests/unit/test_split_calc.py
"""Split calculation unit tests (no DB)."""

from decimal import Decimal

from app.services.split_service import SplitService


def test_equal_split_three_people():
    svc = SplitService(session=None)  # type: ignore[arg-type]
    user_share, parts = svc.calculate(
        total=Decimal("900"),
        split_type="equal",
        split_with=["Ravi", "Priya"],
    )
    assert user_share == Decimal("300.00")
    assert len(parts) == 2
    assert sum((p["amount_owed"] for p in parts), Decimal("0")) + user_share == Decimal("900.00")


def test_they_paid_equal():
    svc = SplitService(session=None)  # type: ignore[arg-type]
    user_share, parts = svc.calculate(
        total=Decimal("480"),
        split_type="equal",
        split_with=["Surya"],
        split_total_people=2,
        split_payer="Surya",
    )
    assert user_share == Decimal("240.00")
    assert parts[0]["direction"] == "i_owe_them"


def test_percent_split():
    svc = SplitService(session=None)  # type: ignore[arg-type]
    user_share, parts = svc.calculate(
        total=Decimal("900"),
        split_type="percent",
        split_with=["Surya", "Karthik"],
        split_amounts={"me": 40, "Surya": 30, "Karthik": 30},
    )
    assert user_share == Decimal("360.00")
