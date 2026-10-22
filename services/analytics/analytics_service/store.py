"""SQLite storage for clicks. Owned exclusively by the analytics service."""

import sqlite3
import threading

MAX_REFERRER_LENGTH = 512


class ClickStore:
    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS clicks ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " code TEXT NOT NULL,"
                " referrer TEXT,"
                " clicked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def record(self, code: str, referrer: str | None) -> None:
        if referrer is not None:
            referrer = referrer[:MAX_REFERRER_LENGTH]
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO clicks (code, referrer) VALUES (?, ?)", (code, referrer)
            )

    def total_clicks(self, code: str) -> int:
        with self._lock:
            (count,) = self._conn.execute(
                "SELECT COUNT(*) FROM clicks WHERE code = ?", (code,)
            ).fetchone()
        return count
