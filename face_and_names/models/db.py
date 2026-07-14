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
SCHEMA_VERSION = 6


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
    if version < 3:
        _ensure_face_embedding_table(conn)
        version = 3
    if version < 4:
        _ensure_person_name_columns(conn)
        version = 4
    if version < 5:
        _ensure_import_progress_columns(conn)
        version = 5
    if version < 6:
        _ensure_embedding_compatibility_columns(conn)
        version = 6
    if version != to_version:
        raise RuntimeError(f"No migration path from {from_version} to {to_version}")


def _ensure_face_detection_index_column(conn: sqlite3.Connection) -> None:
    """Add face_detection_index column if missing (v1 -> v2)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(face)")}.copy()
    if "face_detection_index" not in cols:
        conn.execute("ALTER TABLE face ADD COLUMN face_detection_index REAL;")
        conn.commit()


def _ensure_face_embedding_table(conn: sqlite3.Connection) -> None:
    """Add versioned face embeddings table (v2 -> v3)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS face_embedding (
            id INTEGER PRIMARY KEY,
            face_id INTEGER NOT NULL REFERENCES face(id) ON DELETE CASCADE,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            crop_sha256 TEXT NOT NULL,
            vector_dim INTEGER NOT NULL,
            vector_dtype TEXT NOT NULL DEFAULT 'float32',
            vector_blob BLOB NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (face_id, model_name, model_version, crop_sha256)
        );

        CREATE INDEX IF NOT EXISTS idx_face_embedding_face_id ON face_embedding(face_id);
        CREATE INDEX IF NOT EXISTS idx_face_embedding_model
            ON face_embedding(model_name, model_version);
        """
    )
    conn.commit()


def _ensure_person_name_columns(conn: sqlite3.Connection) -> None:
    """Add person display-name columns (v3 -> v4)."""
    if (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'person'"
        ).fetchone()
        is None
    ):
        return
    cols = {row[1] for row in conn.execute("PRAGMA table_info(person)")}
    if "first_name" not in cols:
        conn.execute("ALTER TABLE person ADD COLUMN first_name TEXT NOT NULL DEFAULT ''")
    if "last_name" not in cols:
        conn.execute("ALTER TABLE person ADD COLUMN last_name TEXT NOT NULL DEFAULT ''")
    if "short_name" not in cols:
        conn.execute("ALTER TABLE person ADD COLUMN short_name TEXT")
    conn.commit()


def _ensure_import_progress_columns(conn: sqlite3.Connection) -> None:
    """Add resumable import state (v4 -> v5)."""
    if (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'import_session'"
        ).fetchone()
        is None
    ):
        return
    cols = {row[1] for row in conn.execute("PRAGMA table_info(import_session)")}
    if "status" not in cols:
        conn.execute(
            "ALTER TABLE import_session ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'"
        )
    if "next_index" not in cols:
        conn.execute("ALTER TABLE import_session ADD COLUMN next_index INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def _ensure_embedding_compatibility_columns(conn: sqlite3.Connection) -> None:
    """Add preprocessing compatibility metadata (v5 -> v6)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(face_embedding)")}
    additions = {
        "preprocessing_version": "TEXT NOT NULL DEFAULT 'unknown'",
        "input_normalization": "TEXT NOT NULL DEFAULT 'unknown'",
        "similarity_metric": "TEXT NOT NULL DEFAULT 'unknown'",
        "crop_strategy": "TEXT NOT NULL DEFAULT 'unknown'",
    }
    for name, definition in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE face_embedding ADD COLUMN {name} {definition}")
    conn.commit()
