"""SQLite storage for short links. Owned exclusively by the link service."""

import secrets
import sqlite3
import string
import threading
from dataclasses import dataclass

CODE_ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7
MAX_CODE_ATTEMPTS = 5


@dataclass(frozen=True)
class Link:
    code: str
    url: str


class CodeGenerationError(RuntimeError):
    """Raised when no free short code could be generated."""


class LinkStore:
    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS links ("
                " code TEXT PRIMARY KEY,"
                " url TEXT NOT NULL,"
                " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def create(self, url: str) -> Link:
        for _ in range(MAX_CODE_ATTEMPTS):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            try:
                with self._lock, self._conn:
                    self._conn.execute("INSERT INTO links (code, url) VALUES (?, ?)", (code, url))
                return Link(code=code, url=url)
            except sqlite3.IntegrityError:
                continue
        raise CodeGenerationError("Could not generate a unique short code")

    def get(self, code: str) -> Link | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT code, url FROM links WHERE code = ?", (code,)
            ).fetchone()
        return Link(code=row[0], url=row[1]) if row else None
