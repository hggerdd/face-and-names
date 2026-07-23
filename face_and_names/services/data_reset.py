"""
Helpers to reset image/face data while keeping people/groups intact.
"""

from __future__ import annotations

import json
import sqlite3

from face_and_names.models.repositories import AuditLogRepository


def reset_image_data(conn: sqlite3.Connection) -> None:
    """
    Delete image- and face-related rows but keep person/group tables untouched.
    """
    conn.execute("DELETE FROM face")
    conn.execute("DELETE FROM metadata")
    conn.execute("DELETE FROM image")
    conn.execute("DELETE FROM import_session")
    conn.execute("DELETE FROM stats")
    AuditLogRepository(conn).add(
        action="reset_image_data",
        entity_type="database",
        details=json.dumps({"scope": "images_faces_metadata_imports_stats"}),
    )
    conn.commit()
