# tests/integration/test_category_corrections.py
"""User category corrections persist and appear in NLP prompt block."""

from __future__ import annotations

import pytest

from app.services.category_service import CategoryService


@pytest.mark.asyncio
async def test_correction_injected_into_prompt(db_session, test_user):
    cats = CategoryService(db_session)
    await cats.record_correction(test_user.id, "medicine", "medical")
    block = await cats.get_user_corrections_for_prompt(test_user.id)
    assert "medicine" in block
    assert "medical" in block


@pytest.mark.asyncio
async def test_categories_for_prompt_lists_defaults(db_session, test_user):
    cats = CategoryService(db_session)
    listing = await cats.get_categories_for_prompt(test_user.id)
    assert "fuel" in listing
    assert "food_outside" in listing
