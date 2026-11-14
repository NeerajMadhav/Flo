# app/channels/telegram/keyboards.py
"""Inline keyboard builders."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_expense_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Save", callback_data="expense:confirm"),
                InlineKeyboardButton("✏️ Edit", callback_data="expense:edit"),
                InlineKeyboardButton("❌ Cancel", callback_data="expense:cancel"),
            ]
        ]
    )


def confirm_split_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Save", callback_data="split:confirm"),
                InlineKeyboardButton("✏️ Edit", callback_data="split:edit"),
                InlineKeyboardButton("❌ Cancel", callback_data="split:cancel"),
            ]
        ]
    )


def confirm_settlement_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm", callback_data="settle:confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="settle:cancel"),
            ]
        ]
    )


def edit_field_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Amount", callback_data="edit:amount"),
                InlineKeyboardButton("Category", callback_data="edit:category"),
            ],
            [
                InlineKeyboardButton("Date", callback_data="edit:date"),
                InlineKeyboardButton("Description", callback_data="edit:description"),
            ],
            [InlineKeyboardButton("« Back", callback_data="edit:back")],
        ]
    )


def alias_keyboard(name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"Yes, alias of existing", callback_data="alias:yes"),
                InlineKeyboardButton(f"No, new person", callback_data="alias:no"),
            ]
        ]
    )
