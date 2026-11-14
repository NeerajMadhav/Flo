# tests/unit/test_split_calculations.py
"""All 4 split types + rounding + validation errors."""

from decimal import Decimal

import pytest

from app.core.exceptions import SplitValidationError
from app.services.split_service import SplitService


@pytest.fixture
def svc():
    return SplitService(session=None)  # type: ignore[arg-type]


def test_equal_two_people(svc):
    user_share, parts = svc.calculate(
        total=Decimal("100"), split_type="equal", split_with=["Ravi"]
    )
    assert user_share + parts[0]["amount_owed"] == Decimal("100.00")
    assert parts[0]["direction"] == "they_owe_me"


def test_equal_three_way_uneven_paise(svc):
    """₹100 / 3 does not divide evenly — remainder absorbed, still sums to 100."""
    user_share, parts = svc.calculate(
        total=Decimal("100"),
        split_type="equal",
        split_with=["Ravi", "Priya"],
    )
    total = user_share + sum((p["amount_owed"] for p in parts), Decimal("0"))
    assert total == Decimal("100.00")
    assert len(parts) == 2


def test_equal_they_paid(svc):
    user_share, parts = svc.calculate(
        total=Decimal("480"),
        split_type="equal",
        split_with=["Surya"],
        split_total_people=2,
        split_payer="Surya",
    )
    assert user_share == Decimal("240.00")
    assert parts[0]["direction"] == "i_owe_them"
    assert parts[0]["person_name"] == "Surya"


def test_custom_exact_match(svc):
    user_share, parts = svc.calculate(
        total=Decimal("1200"),
        split_type="custom",
        split_with=["Ravi", "Priya"],
        split_amounts={"me": 600, "Ravi": 400, "Priya": 200},
    )
    assert user_share == Decimal("600.00")
    assert sum((p["amount_owed"] for p in parts), Decimal("0")) == Decimal("600.00")


def test_custom_mismatch_raises(svc):
    with pytest.raises(SplitValidationError) as ei:
        svc.calculate(
            total=Decimal("1000"),
            split_type="custom",
            split_with=["Ravi"],
            split_amounts={"me": 400, "Ravi": 400},
        )
    assert "800" in ei.value.message or "1000" in ei.value.message


def test_percent_within_tolerance(svc):
    user_share, parts = svc.calculate(
        total=Decimal("1000"),
        split_type="percent",
        split_with=["A", "B"],
        split_amounts={"me": 33.3, "A": 33.4, "B": 33.3},
    )
    assert user_share == Decimal("333.00")


def test_percent_below_tolerance_fails(svc):
    with pytest.raises(SplitValidationError):
        svc.calculate(
            total=Decimal("1000"),
            split_type="percent",
            split_with=["A"],
            split_amounts={"me": 40, "A": 55},  # 95%
        )


def test_shares_2_to_1(svc):
    user_share, parts = svc.calculate(
        total=Decimal("480"),
        split_type="shares",
        split_with=["Ravi"],
        split_amounts={"me": 2, "Ravi": 1},
    )
    assert user_share == Decimal("320.00")
    assert parts[0]["amount_owed"] == Decimal("160.00")


def test_equal_needs_two_people(svc):
    with pytest.raises(SplitValidationError):
        svc.calculate(total=Decimal("100"), split_type="equal", split_with=[])
