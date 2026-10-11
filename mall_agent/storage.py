"""对话历史 SQLite 持久化"""

import os
import json
import time
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db_path() -> str:
    path = os.getenv("CHAT_DB_PATH") or os.path.join(BASE_DIR, "data", "chat.db")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                title      TEXT,
                updated_at REAL,
                messages   TEXT
            )
            """
        )


def _make_title(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") == "user":
            text = str(m.get("content", "")).strip().replace("\n", " ")
            return text[:24] + ("…" if len(text) > 24 else "")
    return "新对话"


def save_session(session_id: str, messages: list[dict], title: str | None = None) -> None:
    if not session_id:
        return
    init_db()
    payload = json.dumps(messages, ensure_ascii=False)
    title = title or _make_title(messages)
    ts = time.time()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions(session_id, title, updated_at, messages)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                title = excluded.title,
                updated_at = excluded.updated_at,
                messages = excluded.messages
            """,
            (session_id, title, ts, payload),
        )


def load_session(session_id: str) -> tuple[str, list[dict]] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT title, messages FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    try:
        messages = json.loads(row["messages"])
    except json.JSONDecodeError:
        messages = []
    return row["title"], messages


def latest_session() -> tuple[str, str, list[dict]] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT session_id, title, messages FROM sessions ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    try:
        messages = json.loads(row["messages"])
    except json.JSONDecodeError:
        messages = []
    return row["session_id"], row["title"], messages


def list_sessions(limit: int = 50) -> list[tuple[str, str]]:
    """返回 [(显示标题, session_id), ...]，按更新时间倒序。"""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT session_id, title, updated_at FROM sessions "
            "WHERE messages != '[]' ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [(r["title"] or "未命名对话", r["session_id"]) for r in rows]


def delete_session(session_id: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
