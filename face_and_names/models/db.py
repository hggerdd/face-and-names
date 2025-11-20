"""
SQLite access helpers for Face-and-Names v2.

Responsibilities:
- Configure SQLite connection defaults (foreign keys on).
- Apply the bundled schema from `schema.sql`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


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
    conn = connect(db_path)
    apply_schema(conn)
    return conn
