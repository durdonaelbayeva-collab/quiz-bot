"""
SQLite database layer (via aiosqlite) for the simple quiz bot.
One file, no server needed -- easy to deploy anywhere.

Schema:
  quizzes(id, title, created_at)
  questions(id, quiz_id, text, explanation)
  options(id, question_id, text, is_correct)
  attempts(id, user_id, quiz_id, score, total, finished_at)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import aiosqlite

DB_PATH = os.getenv("DB_PATH", "quiz_bot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    explanation TEXT
);

CREATE TABLE IF NOT EXISTS options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    quiz_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    finished_at TEXT NOT NULL
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


# ---------- Quizzes ----------

async def create_quiz(title: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO quizzes (title, created_at) VALUES (?, ?)",
            (title, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
        return cursor.lastrowid


async def list_quizzes() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT q.id, q.title, COUNT(qs.id) as question_count
               FROM quizzes q LEFT JOIN questions qs ON qs.quiz_id = q.id
               GROUP BY q.id ORDER BY q.id DESC"""
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_quiz(quiz_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
        await db.commit()


async def get_quiz(quiz_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


# ---------- Questions / Options ----------

async def add_question(quiz_id: int, text: str, options: list[tuple[str, bool]], explanation: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO questions (quiz_id, text, explanation) VALUES (?, ?, ?)",
            (quiz_id, text, explanation),
        )
        question_id = cursor.lastrowid
        for opt_text, is_correct in options:
            await db.execute(
                "INSERT INTO options (question_id, text, is_correct) VALUES (?, ?, ?)",
                (question_id, opt_text, int(is_correct)),
            )
        await db.commit()
        return question_id


async def get_questions(quiz_id: int) -> list[dict]:
    """Returns questions with their options nested under 'options'."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM questions WHERE quiz_id = ?", (quiz_id,))
        questions = [dict(r) for r in await cursor.fetchall()]

        for q in questions:
            opt_cursor = await db.execute("SELECT * FROM options WHERE question_id = ?", (q["id"],))
            q["options"] = [dict(r) for r in await opt_cursor.fetchall()]

        return questions


async def question_count(quiz_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM questions WHERE quiz_id = ?", (quiz_id,))
        row = await cursor.fetchone()
        return row[0]


# ---------- Attempts ----------

async def save_attempt(user_id: int, quiz_id: int, score: int, total: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO attempts (user_id, quiz_id, score, total, finished_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, quiz_id, score, total, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def user_history(user_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT a.*, q.title as quiz_title FROM attempts a
               JOIN quizzes q ON q.id = a.quiz_id
               WHERE a.user_id = ? ORDER BY a.finished_at DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]
