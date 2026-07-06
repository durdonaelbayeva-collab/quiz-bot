"""
Simple Quiz Bot -- single-purpose Telegram bot for quick tests.

Admin can:
  - create a quiz (just a title)
  - bulk-add questions by pasting formatted text (many at once, not one by one)
  - bulk-add questions by uploading a PDF prepared in the same text format
    (the bot extracts the text and parses it automatically)
  - list/delete quizzes

Users can:
  - pick a quiz, answer questions one by one with instant feedback
  - see their score at the end and their past attempt history

Run with: python bot.py   (reads BOT_TOKEN / ADMIN_IDS / DB_PATH from .env)
"""
from __future__ import annotations

import asyncio
import os
import tempfile

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from dotenv import load_dotenv

import database as db
import keyboards as kb
from parser import extract_text_from_pdf, parse_bulk_text
from states import BulkAddPdf, BulkAddText, CreateQuiz, TakingQuiz

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

dp = Dispatcher(storage=MemoryStorage())


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ---------------------------------------------------------------------------
# Basic navigation
# ---------------------------------------------------------------------------

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Xush kelibsiz! Bu — test/quiz bot.\n\nQuyidagi menyudan foydalaning:",
        reply_markup=kb.main_menu_kb(),
    )


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Sizda admin huquqi yo'q.")
        return
    await message.answer("🛠 Admin panel:", reply_markup=kb.admin_menu_kb())


@dp.message(F.text == "⬅️ Asosiy menyu")
async def back_to_main(message: Message):
    await message.answer("Asosiy menyu:", reply_markup=kb.main_menu_kb())


# ---------------------------------------------------------------------------
# ADMIN: create quiz
# ---------------------------------------------------------------------------

@dp.message(F.text == "➕ Yangi test yaratish")
async def create_quiz_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("📘 Yangi test nomini kiriting (masalan: Chizmachilik — 1-bo'lim):")
    await state.set_state(CreateQuiz.title)


@dp.message(CreateQuiz.title, F.text)
async def create_quiz_save(message: Message, state: FSMContext):
    quiz_id = await db.create_quiz(message.text.strip())
    await state.clear()
    await message.answer(
        f"✅ Test yaratildi (ID: {quiz_id}). Endi unga savol qo'shishingiz mumkin:\n"
        "'✍️ Savol qo'shish (matn)' yoki '📄 Savol qo'shish (PDF)' tugmasidan foydalaning."
    )


# ---------------------------------------------------------------------------
# ADMIN: bulk add questions via pasted text
# ---------------------------------------------------------------------------

BULK_FORMAT_HELP = (
    "✍️ <b>Savollarni matn qilib joylashtiring.</b>\n\n"
    "Har bir savol quyidagicha yoziladi, savollar orasida BO'SH QATOR qoldiring:\n\n"
    "<code>Ranglar nazariyasida asosiy ranglar nechta?\n"
    "A) 2\n"
    "B) 3*\n"
    "C) 4\n"
    "D) 5</code>\n\n"
    "❗️ To'g'ri javobning oxiriga <b>*</b> belgisini qo'ying.\n"
    "Bir xabarda bir nechta savol yuborishingiz mumkin — bittalab kiritish shart emas."
)


@dp.message(F.text == "✍️ Savol qo'shish (matn)")
async def bulk_text_choose_quiz(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    quizzes = await db.list_quizzes()
    if not quizzes:
        await message.answer("⚠️ Avval test yarating ('➕ Yangi test yaratish').")
        return
    await message.answer("Qaysi testga savol qo'shamiz?", reply_markup=kb.quizzes_kb(quizzes, prefix="addto"))
    await state.set_state(BulkAddText.choose_quiz)


@dp.callback_query(BulkAddText.choose_quiz, F.data.startswith("addto:"))
async def bulk_text_wait_paste(callback: CallbackQuery, state: FSMContext):
    quiz_id = int(callback.data.split(":")[1])
    await state.update_data(quiz_id=quiz_id)
    await state.set_state(BulkAddText.paste_text)
    await callback.message.answer(BULK_FORMAT_HELP)
    await callback.answer()


@dp.message(BulkAddText.paste_text, F.text)
async def bulk_text_save(message: Message, state: FSMContext):
    data = await state.get_data()
    quiz_id = data["quiz_id"]

    parsed = parse_bulk_text(message.text)
    for q in parsed.questions:
        await db.add_question(quiz_id, q.text, q.options)

    report = f"✅ {len(parsed.questions)} ta savol muvaffaqiyatli qo'shildi."
    if parsed.errors:
        report += (
            f"\n⚠️ {len(parsed.errors)} ta blok tushunarsiz format tufayli o'tkazib yuborildi. "
            f"Formatni tekshirib qayta yuboring:\n\n"
            + "\n---\n".join(parsed.errors[:3])
        )
    await message.answer(report)

    if parsed.questions:
        await state.clear()
    # if nothing parsed, stay in the same state so admin can retry pasting


# ---------------------------------------------------------------------------
# ADMIN: bulk add questions via PDF upload
# ---------------------------------------------------------------------------

@dp.message(F.text == "📄 Savol qo'shish (PDF)")
async def bulk_pdf_choose_quiz(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    quizzes = await db.list_quizzes()
    if not quizzes:
        await message.answer("⚠️ Avval test yarating ('➕ Yangi test yaratish').")
        return
    await message.answer("Qaysi testga savol qo'shamiz?", reply_markup=kb.quizzes_kb(quizzes, prefix="pdfto"))
    await state.set_state(BulkAddPdf.choose_quiz)


@dp.callback_query(BulkAddPdf.choose_quiz, F.data.startswith("pdfto:"))
async def bulk_pdf_wait_file(callback: CallbackQuery, state: FSMContext):
    quiz_id = int(callback.data.split(":")[1])
    await state.update_data(quiz_id=quiz_id)
    await state.set_state(BulkAddPdf.upload_pdf)
    await callback.message.answer(
        "📄 PDF faylni yuboring. Fayl ichida savollar xuddi shu formatda bo'lishi kerak:\n\n"
        + BULK_FORMAT_HELP
    )
    await callback.answer()


@dp.message(BulkAddPdf.upload_pdf, F.document)
async def bulk_pdf_process(message: Message, state: FSMContext, bot: Bot):
    if not message.document.file_name.lower().endswith(".pdf"):
        await message.answer("❌ Faqat PDF fayl yuboring.")
        return

    data = await state.get_data()
    quiz_id = data["quiz_id"]

    await message.answer("⏳ PDF o'qilmoqda...")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        await bot.download(message.document, destination=tmp.name)
        tmp_path = tmp.name

    try:
        text = extract_text_from_pdf(tmp_path)
    except Exception as e:
        await message.answer(f"❌ PDF o'qishda xatolik: {e}")
        return
    finally:
        os.unlink(tmp_path)

    parsed = parse_bulk_text(text)
    for q in parsed.questions:
        await db.add_question(quiz_id, q.text, q.options)

    report = f"✅ PDF'dan {len(parsed.questions)} ta savol muvaffaqiyatli qo'shildi."
    if parsed.errors:
        report += (
            f"\n⚠️ {len(parsed.errors)} ta qism tanib bo'lmadi (format mos kelmadi). "
            "Bu qismlarni qo'lda, matn orqali ('✍️ Savol qo'shish (matn)') qo'shing:\n\n"
            + "\n---\n".join(parsed.errors[:3])
        )
    await message.answer(report)
    await state.clear()


# ---------------------------------------------------------------------------
# ADMIN: list / delete quizzes
# ---------------------------------------------------------------------------

@dp.message(F.text == "📋 Testlar ro'yxati")
async def list_quizzes_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    quizzes = await db.list_quizzes()
    if not quizzes:
        await message.answer("Hozircha testlar yo'q.")
        return
    await message.answer("📋 Testlar (o'chirish uchun 🗑 bosing):", reply_markup=kb.quizzes_manage_kb(quizzes))


@dp.callback_query(F.data.startswith("delquiz:"))
async def confirm_delete_quiz(callback: CallbackQuery):
    quiz_id = int(callback.data.split(":")[1])
    await callback.message.answer("Rostdan ham bu testni o'chirmoqchimisiz? (Barcha savollari ham o'chadi)",
                                   reply_markup=kb.confirm_delete_kb(quiz_id))
    await callback.answer()


@dp.callback_query(F.data.startswith("confirmdel:"))
async def do_delete_quiz(callback: CallbackQuery):
    quiz_id = int(callback.data.split(":")[1])
    await db.delete_quiz(quiz_id)
    await callback.message.edit_text("🗑 Test o'chirildi.")
    await callback.answer()


@dp.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery):
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.answer()


@dp.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


# ---------------------------------------------------------------------------
# USER: take a quiz
# ---------------------------------------------------------------------------

@dp.message(F.text == "📝 Test topshirish")
async def user_choose_quiz(message: Message):
    quizzes = await db.list_quizzes()
    quizzes = [q for q in quizzes if q["question_count"] > 0]
    if not quizzes:
        await message.answer("⚠️ Hozircha savollari bo'lgan test mavjud emas.")
        return
    await message.answer("📘 Testni tanlang:", reply_markup=kb.quizzes_kb(quizzes, prefix="take"))


@dp.callback_query(F.data.startswith("take:"))
async def start_quiz(callback: CallbackQuery, state: FSMContext):
    quiz_id = int(callback.data.split(":")[1])
    questions = await db.get_questions(quiz_id)
    if not questions:
        await callback.answer("Bu testda savollar yo'q.", show_alert=True)
        return

    await state.update_data(
        quiz_id=quiz_id,
        q_index=0,
        correct_count=0,
        questions_cache={str(q["id"]): q for q in questions},
        question_ids=[q["id"] for q in questions],
    )
    await state.set_state(TakingQuiz.running)
    await callback.message.edit_text(f"🚀 Test boshlandi! Jami savollar: {len(questions)}")
    await send_question(callback.message, state)
    await callback.answer()


async def send_question(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    idx = data["q_index"]
    q_ids = data["question_ids"]

    if idx >= len(q_ids):
        await finish_quiz(message, state)
        return

    q_id = q_ids[idx]
    q = data["questions_cache"][str(q_id)]
    await message.answer(
        f"❓ Savol {idx + 1}/{len(q_ids)}:\n\n{q['text']}",
        reply_markup=kb.option_kb(q_id, q["options"]),
    )


@dp.callback_query(TakingQuiz.running, F.data.startswith("ans:"))
async def handle_answer(callback: CallbackQuery, state: FSMContext):
    _, q_id_str, opt_id_str = callback.data.split(":")
    q_id, opt_id = int(q_id_str), int(opt_id_str)

    data = await state.get_data()
    q = data["questions_cache"][str(q_id)]
    correct_opt = next(o for o in q["options"] if o["is_correct"])
    is_correct = opt_id == correct_opt["id"]

    correct_count = data["correct_count"] + (1 if is_correct else 0)
    new_index = data["q_index"] + 1
    await state.update_data(q_index=new_index, correct_count=correct_count)

    feedback = "✅ To'g'ri!" if is_correct else f"❌ Noto'g'ri. To'g'ri javob: {correct_opt['text']}"
    try:
        await callback.message.edit_text(f"{callback.message.text}\n\n{feedback}")
    except Exception:
        pass
    await callback.answer()

    await send_question(callback.message, state)


async def finish_quiz(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    total = len(data["question_ids"])
    correct = data["correct_count"]
    percent = round(correct / total * 100, 1) if total else 0

    await db.save_attempt(message.chat.id, data["quiz_id"], correct, total)
    await state.clear()

    await message.answer(
        f"🏁 <b>Test yakunlandi!</b>\n\n"
        f"✅ To'g'ri javoblar: {correct}/{total}\n"
        f"📊 Natija: <b>{percent}%</b>",
        reply_markup=kb.main_menu_kb(),
    )


# ---------------------------------------------------------------------------
# USER: history
# ---------------------------------------------------------------------------

@dp.message(F.text == "📊 Natijalarim")
async def show_history(message: Message):
    history = await db.user_history(message.chat.id)
    if not history:
        await message.answer("Hali test topshirmagansiz.")
        return
    lines = ["📊 <b>Oxirgi natijalaringiz:</b>\n"]
    for h in history:
        percent = round(h["score"] / h["total"] * 100, 1) if h["total"] else 0
        lines.append(f"• {h['quiz_title']} — {h['score']}/{h['total']} ({percent}%)")
    await message.answer("\n".join(lines))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi. .env faylini tekshiring.")

    await db.init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
