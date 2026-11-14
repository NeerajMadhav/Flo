# app/main.py
"""FastAPI entrypoint — lifespan wires DB, Telegram bot, scheduler."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.channels.api.middleware import APIRateLimitMiddleware, RequestIdMiddleware
from app.channels.api.v1.router import api_router
from app.channels.telegram.application import (
    build_application,
    register_webhook,
    setup_bot_commands,
)
from app.channels.telegram.router import webhook_router
from app.config import get_settings
from app.core.database import AsyncSessionLocal, create_all_tables
from app.core.exceptions import (
    ExpenseNotFoundError,
    FloBaseException,
    UserNotFoundError,
    UserNotOnboardedError,
)
from app.core.seed import seed_categories
from app.scheduler.jobs import start_scheduler
from app.utils.logger import get_logger, log_event

logger = get_logger("flo.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log_event(logger, "app.starting", version=settings.app_version, mode=settings.bot_mode)

    await create_all_tables()
    await seed_categories()

    ptb = build_application()
    await ptb.initialize()
    await setup_bot_commands(ptb)

    scheduler = start_scheduler(ptb.bot)
    polling_task = None

    if settings.bot_mode == "webhook":
        await ptb.start()
        await register_webhook(ptb)
        log_event(logger, "bot.webhook_registered", url=settings.backend_url)
    else:
        # Local/dev polling — no public URL needed
        await ptb.start()
        if ptb.updater:
            await ptb.updater.start_polling(drop_pending_updates=True)
            log_event(logger, "bot.polling_started")
        else:
            log_event(logger, "bot.polling_unavailable")

    app.state.ptb = ptb
    app.state.scheduler = scheduler

    yield

    log_event(logger, "app.stopping")
    if scheduler:
        scheduler.shutdown(wait=False)
    if ptb.updater and ptb.updater.running:
        await ptb.updater.stop()
    await ptb.stop()
    await ptb.shutdown()


app = FastAPI(title="Flo", version=get_settings().app_version, lifespan=lifespan)
# Starlette runs last-added middleware first — RequestId must wrap rate-limit
app.add_middleware(APIRateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
app.include_router(webhook_router)
app.include_router(api_router)


@app.exception_handler(FloBaseException)
async def flo_exception_handler(request: Request, exc: FloBaseException):
    status = 400
    if isinstance(exc, (ExpenseNotFoundError, UserNotFoundError)):
        status = 404
    elif isinstance(exc, UserNotOnboardedError):
        status = 403
    return JSONResponse(status_code=status, content={"detail": exc.message})


@app.get("/health")
async def health():
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "db_status": db_status,
        "version": get_settings().app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
