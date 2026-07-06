"""Reply and inline keyboards for the simple quiz bot."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
)


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Test topshirish")],
            [KeyboardButton(text="📊 Natijalarim")],
        ],
        resize_keyboard=True,
    )


def admin_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Yangi test yaratish")],
            [KeyboardButton(text="✍️ Savol qo'shish (matn)")],
            [KeyboardButton(text="📄 Savol qo'shish (PDF)")],
            [KeyboardButton(text="📋 Testlar ro'yxati")],
            [KeyboardButton(text="⬅️ Asosiy menyu")],
        ],
        resize_keyboard=True,
    )


def quizzes_kb(quizzes: list[dict], prefix: str = "quiz") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"📘 {q['title']} ({q['question_count']} ta savol)",
            callback_data=f"{prefix}:{q['id']}",
        )]
        for q in quizzes
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quizzes_manage_kb(quizzes: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for q in quizzes:
        rows.append([
            InlineKeyboardButton(text=f"📘 {q['title']} ({q['question_count']} ta)", callback_data="noop"),
            InlineKeyboardButton(text="🗑", callback_data=f"delquiz:{q['id']}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def option_kb(question_id: int, options: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=opt["text"], callback_data=f"ans:{question_id}:{opt['id']}")]
        for opt in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_kb(quiz_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, o'chirish", callback_data=f"confirmdel:{quiz_id}"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel"),
    ]])
