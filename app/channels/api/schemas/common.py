# app/channels/api/schemas/common.py
"""Shared API response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class MessageOut(BaseModel):
    message: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
