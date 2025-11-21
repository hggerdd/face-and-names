"""
Helpers to reset image/face data while keeping people/groups intact.
"""

from __future__ import annotations

import sqlite3


def reset_image_data(conn: sqlite3.Connection) -> None:
    """
    Delete image- and face-related rows but keep person/group tables untouched.
    """
    conn.execute("DELETE FROM face")
    conn.execute("DELETE FROM metadata")
    conn.execute("DELETE FROM image")
    conn.execute("DELETE FROM import_session")
    conn.execute("DELETE FROM stats")
    conn.execute("DELETE FROM audit_log")
    conn.commit()
