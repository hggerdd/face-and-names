"""
SQLite access helpers for Face-and-Names v2.

Responsibilities:
- Configure SQLite connection defaults (foreign keys on).
- Apply the bundled schema from `schema.sql`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 2


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Set SQLite pragmas before use."""
    conn.execute("PRAGMA foreign_keys = ON;")


def load_schema_sql() -> str:
    """Load the bundled schema.sql file."""
    return SCHEMA_PATH.read_text(encoding="utf-8")


def apply_schema(conn: sqlite3.Connection) -> None:
    """Execute the schema DDL against an open connection."""
    _configure_connection(conn)
    conn.executescript(load_schema_sql())


def _get_schema_version(conn: sqlite3.Connection) -> Optional[int]:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cursor.fetchone() is None:
        return None
    row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    return int(row[0]) if row else None


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT INTO schema_version (id, version) VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET version = excluded.version
        """,
        (version,),
    )
    conn.commit()


def connect(db_path: Path) -> sqlite3.Connection:
    """Create a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    _configure_connection(conn)
    return conn


def initialize_database(db_path: Path) -> sqlite3.Connection:
    """
    Open a connection to the database at `db_path`, creating parent folders and
    applying the bundled schema if the DB is new.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not db_path.exists()
    conn = connect(db_path)

    current_version = _get_schema_version(conn)
    if is_new or current_version is None:
        apply_schema(conn)
        _set_schema_version(conn, SCHEMA_VERSION)
    elif current_version < SCHEMA_VERSION:
        _migrate(conn, current_version, SCHEMA_VERSION)
        _set_schema_version(conn, SCHEMA_VERSION)
    elif current_version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is newer than supported {SCHEMA_VERSION}"
        )
    return conn


def _migrate(conn: sqlite3.Connection, from_version: int, to_version: int) -> None:
    """Apply incremental migrations up to `to_version`."""
    version = from_version
    if version < 2:
        _ensure_face_detection_index_column(conn)
        version = 2
    if version != to_version:
        raise RuntimeError(f"No migration path from {from_version} to {to_version}")


def _ensure_face_detection_index_column(conn: sqlite3.Connection) -> None:
    """Add face_detection_index column if missing (v1 -> v2)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(face)")}.copy()
    if "face_detection_index" not in cols:
        conn.execute("ALTER TABLE face ADD COLUMN face_detection_index REAL;")
        conn.commit()
