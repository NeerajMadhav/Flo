# app/channels/api/v1/router.py
"""Aggregate /api/v1 routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.channels.api.v1 import analytics, auth, expenses, users

api_router = APIRouter(prefix='/api/v1')
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(expenses.router)
api_router.include_router(analytics.router)
