# app/channels/api/v1/auth.py
"""Issue JWT only after Telegram Login Widget HMAC verification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.api.schemas.common import TokenOut
from app.config import get_settings
from app.core.database import get_db
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService
from app.utils.telegram_auth import verify_telegram_login

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramLoginIn(BaseModel):
    """Fields from Telegram Login Widget callback."""

    id: int = Field(..., description="Telegram user id")
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


def _issue_token(user_id: int) -> TokenOut:
    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    token = jwt.encode(
        {"sub": str(user_id), "exp": exp},
        settings.api_secret_key,
        algorithm="HS256",
    )
    return TokenOut(access_token=token)


@router.post("/telegram", response_model=TokenOut)
async def auth_telegram(
    body: TelegramLoginIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Exchange a verified Telegram Login Widget payload for a JWT.

    Root cause fixed: previously accepted bare telegram_user_id with no proof,
    allowing anyone who knew/guessed an ID to mint a token.
    """
    settings = get_settings()
    payload = body.model_dump()
    client_ip = request.client.host if request.client else None
    audit = AuditService(session)

    if not verify_telegram_login(payload, settings.telegram_bot_token):
        await audit.record(
            "auth.login_failed",
            source="api",
            ip_address=client_ip,
            new_value={"reason": "invalid_hmac", "telegram_user_id": str(body.id)},
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="Invalid Telegram login")

    telegram_user_id = str(body.id)
    user = await UserRepository(session).get_by_telegram_id(telegram_user_id)
    if not user or not user.onboarded or not user.is_active:
        await audit.record(
            "auth.login_failed",
            user_id=user.id if user else None,
            source="api",
            ip_address=client_ip,
            new_value={"reason": "user_not_eligible", "telegram_user_id": telegram_user_id},
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="Invalid Telegram login")

    await audit.record(
        "auth.login_success",
        user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        source="api",
        ip_address=client_ip,
    )
    await session.commit()
    return _issue_token(user.id)
