# app/dependencies.py
"""FastAPI dependency injection helpers."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import get_db
from app.core.models import User
from app.repositories.user_repo import UserRepository

security = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    settings = get_settings()
    try:
        payload = jwt.decode(
            creds.credentials, settings.api_secret_key, algorithms=["HS256"]
        )
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await UserRepository(session).get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    # Root cause: blocking the bot set is_active=False but JWT still worked
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account inactive")
    return user


async def require_onboarded(user: User = Depends(get_current_user)) -> User:
    if not user.onboarded:
        raise HTTPException(status_code=403, detail="Complete onboarding first")
    return user


__all__ = ["get_db", "get_current_user", "require_onboarded"]
