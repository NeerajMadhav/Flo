# app/channels/api/middleware.py
"""HTTP rate limiting + request_id correlation for REST API and Telegram webhook."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from time import monotonic

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.utils.logger import get_logger, log_event, new_request_id, request_id_var

logger = get_logger("flo.http")

_windows: dict[str, deque[float]] = defaultdict(deque)
_lock = asyncio.Lock()


def _sanitize_request_id(value: str | None) -> str:
    if not value:
        return new_request_id()
    cleaned = "".join(c for c in value if c.isalnum() or c in "-_")[:64]
    return cleaned or new_request_id()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Honor/assign X-Request-ID and bind it to ContextVar for structured logs."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("x-request-id") or request.headers.get(
            "x-correlation-id"
        )
        rid = _sanitize_request_id(incoming)
        token = request_id_var.set(rid)
        request.state.request_id = rid
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_var.reset(token)


class APIRateLimitMiddleware(BaseHTTPMiddleware):
    """Limit /api/* and /webhook/* requests per client IP."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        settings = get_settings()
        if path.startswith("/api/"):
            limit = settings.rate_limit_api_per_min
            bucket = "api"
        elif path.startswith("/webhook/"):
            limit = settings.webhook_rate_limit_per_min
            bucket = "webhook"
        else:
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        key = f"{bucket}:{client}"
        now = monotonic()
        async with _lock:
            q = _windows[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= limit:
                log_event(
                    logger,
                    "rate_limit.exceeded",
                    level=logging.WARNING,
                    source=bucket,
                    client=client,
                    path=path,
                )
                # Durable audit — short-lived session so HTTP edge stays consistent
                try:
                    from app.core.database import AsyncSessionLocal
                    from app.services.audit_service import AuditService

                    async with AsyncSessionLocal() as session:
                        await AuditService(session).record(
                            "rate_limit.exceeded",
                            source=bucket,
                            ip_address=client,
                            new_value={"path": path},
                            level=logging.WARNING,
                        )
                        await session.commit()
                except Exception as e:
                    log_event(
                        logger,
                        "audit.write_failed",
                        level=logging.ERROR,
                        error=str(e),
                        original_event="rate_limit.exceeded",
                    )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Slow down."},
                )
            q.append(now)
        return await call_next(request)
