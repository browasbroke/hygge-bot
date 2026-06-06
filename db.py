"""
Hygge Kafé — база данных броней (SQLite)
Файл hygge.db создаётся автоматически рядом с ботом.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "hygge.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # dict-like доступ: row["name"]
    return conn


def init_db():
    """Создать таблицу при первом запуске."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                username     TEXT,
                name         TEXT NOT NULL,
                phone        TEXT NOT NULL,
                date         TEXT NOT NULL,
                time         TEXT NOT NULL,
                guests       TEXT NOT NULL,
                comment      TEXT DEFAULT '',
                table_number TEXT DEFAULT '',
                status       TEXT DEFAULT 'pending',
                created_at   TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        try:
            conn.execute("ALTER TABLE bookings ADD COLUMN table_number TEXT DEFAULT ''")
        except Exception:
            pass  # уже есть
        conn.commit()


def add_booking(user_id, username, name, phone, date, time, guests, comment="", table_number=""):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO bookings
               (user_id, username, name, phone, date, time, guests, comment, table_number)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, name, phone, date, time, guests, comment, table_number),
        )
        conn.commit()
        return cur.lastrowid


def get_booking(booking_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM bookings WHERE id = ?", (booking_id,)
        ).fetchone()
        return dict(row) if row else None


def update_status(booking_id, status):
    with get_conn() as conn:
        conn.execute(
            "UPDATE bookings SET status = ? WHERE id = ?",
            (status, booking_id),
        )
        conn.commit()


def get_upcoming(limit=20):
    """Все ожидающие и подтверждённые брони."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM bookings
               WHERE status IN ('pending', 'confirmed')
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_booking(booking_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        conn.commit()


def get_all(limit=30):
    """Все брони (для статистики)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
