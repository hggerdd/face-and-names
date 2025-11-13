from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from pathlib import Path
from typing import Generator, Tuple


class DatabaseContext:
    """Central place for managing SQLite connections and transactions."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    @contextmanager
    def get_connection(self) -> Generator[Tuple[sqlite3.Connection, sqlite3.Cursor], None, None]:
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()
            yield conn, cursor
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        with self.get_connection() as (conn, cursor):
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise
