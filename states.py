"""FSM state groups for the simple quiz bot."""
from aiogram.fsm.state import State, StatesGroup


class CreateQuiz(StatesGroup):
    title = State()


class BulkAddText(StatesGroup):
    choose_quiz = State()
    paste_text = State()


class BulkAddPdf(StatesGroup):
    choose_quiz = State()
    upload_pdf = State()


class TakingQuiz(StatesGroup):
    running = State()
