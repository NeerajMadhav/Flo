# app/channels/telegram/application.py
"""Build and configure the python-telegram-bot Application."""

from __future__ import annotations

from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.channels.telegram import router as tg_router
from app.channels.telegram.handlers import commands
from app.config import get_settings


def build_application() -> Application:
    """Register handlers in order: commands → callbacks → text → non-text → chat member."""
    settings = get_settings()
    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", commands.start_cmd))
    app.add_handler(CommandHandler("help", commands.help_cmd))
    app.add_handler(CommandHandler("cancel", commands.cancel_cmd))
    app.add_handler(CommandHandler("settings", commands.settings_cmd))

    app.add_handler(CallbackQueryHandler(tg_router.dispatch_callback))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, tg_router.dispatch_text)
    )
    app.add_handler(
        MessageHandler(
            filters.ATTACHMENT | filters.VOICE | filters.PHOTO | filters.Sticker.ALL,
            tg_router.dispatch_non_text,
        )
    )
    app.add_handler(
        ChatMemberHandler(
            tg_router.dispatch_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER
        )
    )

    tg_router.ptb_application = app
    return app


async def setup_bot_commands(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Start or welcome back"),
            BotCommand("help", "How to use Riruru (Flo)"),
            BotCommand("settings", "View / update profile"),
            BotCommand("cancel", "Cancel current action"),
        ]
    )


async def register_webhook(app: Application) -> None:
    settings = get_settings()
    url = f"{settings.backend_url}/webhook/telegram"
    await app.bot.set_webhook(
        url=url,
        secret_token=settings.telegram_webhook_secret,
        drop_pending_updates=True,
    )
