# tests/unit/test_state_machine_names.py
"""Known conversation states used by the router."""

EXPECTED_STATES = {
    "NEW",
    "ONBOARD_NAME",
    "ONBOARD_INCOME",
    "ONBOARD_BUDGET",
    "IDLE",
    "CONFIRM_EXPENSE",
    "EDIT_FIELD_SELECT",
    "EDIT_FIELD_VALUE",
    "CONFIRM_SPLIT",
    "CONFIRM_SETTLEMENT",
    "CLARIFYING",
    "ALIAS_RESOLUTION",
}


def test_idle_constant():
    from app.services.state_service import IDLE

    assert IDLE == "IDLE"
    assert IDLE in EXPECTED_STATES
