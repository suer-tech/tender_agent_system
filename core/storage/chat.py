"""Серверное хранение чат-сессий и сообщений.

Живёт в tenders.db (SQLite). Каждое сообщение/тендеры/заголовок пишутся при
событии от WS-handler. Фронтенд подтягивает через /api/sessions.

Таблицы:
  chat_sessions(id, title, created_at, updated_at, tenders_json)
  chat_messages(id, session_id, role, content, timestamp)

Тендеры храним как JSON-строку в sessions.tenders_json — последний набор
результатов для сессии. Старые перезаписываются новыми (как и в UI).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "tenders.db"


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT,
            updated_at TEXT,
            tenders_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at DESC);

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, timestamp);
        """)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def upsert_session(session_id: str, title: str | None = None,
                   tenders: list[dict] | None = None) -> None:
    now = _now()
    with conn() as c:
        exists = c.execute("SELECT id FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
        if exists:
            fields = ["updated_at=?"]; args: list = [now]
            if title is not None:
                fields.append("title=?"); args.append(title)
            if tenders is not None:
                fields.append("tenders_json=?"); args.append(json.dumps(tenders, ensure_ascii=False))
            args.append(session_id)
            c.execute(f"UPDATE chat_sessions SET {','.join(fields)} WHERE id=?", args)
        else:
            c.execute(
                "INSERT INTO chat_sessions (id, title, created_at, updated_at, tenders_json) "
                "VALUES (?,?,?,?,?)",
                (
                    session_id,
                    title or "Новый поиск",
                    now, now,
                    json.dumps(tenders or [], ensure_ascii=False),
                ),
            )


def add_message(session_id: str, role: str, content: str) -> None:
    """Сохранить сообщение. Попутно upsert'ит сессию (если её ещё нет)."""
    now = _now()
    with conn() as c:
        exists = c.execute("SELECT id FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
        if not exists:
            c.execute(
                "INSERT INTO chat_sessions (id, title, created_at, updated_at, tenders_json) "
                "VALUES (?,?,?,?,?)",
                (session_id, "Новый поиск", now, now, "[]"),
            )
        c.execute(
            "INSERT INTO chat_messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
            (session_id, role, content, now),
        )
        c.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now, session_id))


def list_sessions(limit: int = 50) -> list[dict]:
    with conn() as c:
        rows = c.execute("""
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS messages_count
            FROM chat_sessions s
            ORDER BY s.updated_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    with conn() as c:
        s = c.execute(
            "SELECT id, title, created_at, updated_at, tenders_json FROM chat_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if not s:
            return None
        messages = c.execute(
            "SELECT id, role, content, timestamp FROM chat_messages "
            "WHERE session_id=? ORDER BY timestamp, id",
            (session_id,),
        ).fetchall()
        return {
            "id": s["id"],
            "title": s["title"],
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
            "tenders": json.loads(s["tenders_json"] or "[]"),
            "messages": [dict(m) for m in messages],
        }


def delete_session(session_id: str) -> bool:
    with conn() as c:
        r = c.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
        # CASCADE удалит messages автоматически (если включён FK). На всякий случай:
        c.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
        return r.rowcount > 0
