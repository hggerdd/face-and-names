"""
Database repositories for common CRUD paths.

These are intentionally lightweight wrappers around sqlite3 connections to keep
business logic in services while centralizing SQL and schema assumptions.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, Mapping, Sequence


class ImportSessionRepository:
    """Manage import_session rows."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, folder_count: int, image_count: int = 0) -> int:
        cursor = self.conn.execute(
            "INSERT INTO import_session (folder_count, image_count) VALUES (?, ?)",
            (folder_count, image_count),
        )
        return int(cursor.lastrowid)

    def increment_image_count(self, session_id: int, delta: int = 1) -> None:
        self.conn.execute(
            "UPDATE import_session SET image_count = image_count + ? WHERE id = ?",
            (delta, session_id),
        )

    def get(self, session_id: int) -> tuple[int, int, int]:
        cursor = self.conn.execute(
            "SELECT id, folder_count, image_count FROM import_session WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Import session {session_id} not found")
        return int(row[0]), int(row[1]), int(row[2])


class ImageRepository:
    """Access to image rows."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        import_id: int,
        relative_path: str,
        sub_folder: str,
        filename: str,
        content_hash: bytes,
        perceptual_hash: int,
        width: int,
        height: int,
        orientation_applied: int,
        has_faces: int,
        thumbnail_path: str,
        size_bytes: int,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO image (
                import_id, relative_path, sub_folder, filename,
                content_hash, perceptual_hash, width, height,
                orientation_applied, has_faces, thumbnail_path, size_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                import_id,
                relative_path,
                sub_folder,
                filename,
                sqlite3.Binary(content_hash),
                perceptual_hash,
                width,
                height,
                orientation_applied,
                has_faces,
                thumbnail_path,
                size_bytes,
            ),
        )
        return int(cursor.lastrowid)

    def get_by_content_hash(self, content_hash: bytes) -> int | None:
        cursor = self.conn.execute(
            "SELECT id FROM image WHERE content_hash = ?", (sqlite3.Binary(content_hash),)
        )
        row = cursor.fetchone()
        return int(row[0]) if row else None

    def set_thumbnail_path(self, image_id: int, thumbnail_path: str) -> None:
        self.conn.execute(
            "UPDATE image SET thumbnail_path = ? WHERE id = ?",
            (thumbnail_path, image_id),
        )


class MetadataRepository:
    """Metadata key/value storage per image."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_entries(self, image_id: int, entries: Mapping[str, str], meta_type: str) -> None:
        self.conn.executemany(
            "INSERT INTO metadata (image_id, key, type, value) VALUES (?, ?, ?, ?)",
            ((image_id, key, meta_type, value) for key, value in entries.items()),
        )


class FaceRepository:
    """Store detected or annotated faces."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        image_id: int,
        bbox_abs: Sequence[float],
        bbox_rel: Sequence[float],
        face_crop_path: str,
        provenance: str,
        cluster_id: int | None = None,
        person_id: int | None = None,
        predicted_person_id: int | None = None,
        prediction_confidence: float | None = None,
    ) -> int:
        bx, by, bw, bh = bbox_abs
        brx, bry, brw, brh = bbox_rel
        cursor = self.conn.execute(
            """
            INSERT INTO face (
                image_id, bbox_x, bbox_y, bbox_w, bbox_h,
                bbox_rel_x, bbox_rel_y, bbox_rel_w, bbox_rel_h,
                face_crop_path, cluster_id, person_id, predicted_person_id,
                prediction_confidence, provenance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                image_id,
                bx,
                by,
                bw,
                bh,
                brx,
                bry,
                brw,
                brh,
                face_crop_path,
                cluster_id,
                person_id,
                predicted_person_id,
                prediction_confidence,
                provenance,
            ),
        )
        return int(cursor.lastrowid)


class PersonRepository:
    """CRUD for person records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, primary_name: str, birthdate: str | None = None, notes: str | None = None) -> int:
        cursor = self.conn.execute(
            "INSERT INTO person (primary_name, birthdate, notes) VALUES (?, ?, ?)",
            (primary_name, birthdate, notes),
        )
        return int(cursor.lastrowid)


class PersonAliasRepository:
    """Aliases/short names per person."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_alias(self, person_id: int, name: str, kind: str = "alias") -> int:
        cursor = self.conn.execute(
            "INSERT INTO person_alias (person_id, name, kind) VALUES (?, ?, ?)",
            (person_id, name, kind),
        )
        return int(cursor.lastrowid)


class GroupRepository:
    """CRUD for groups/tags."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(
        self,
        name: str,
        parent_group_id: int | None = None,
        description: str | None = None,
        color: str | None = None,
    ) -> int:
        cursor = self.conn.execute(
            "INSERT INTO \"group\" (name, parent_group_id, description, color) VALUES (?, ?, ?, ?)",
            (name, parent_group_id, description, color),
        )
        return int(cursor.lastrowid)


class PersonGroupRepository:
    """Link people to groups."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_memberships(self, person_id: int, group_ids: Iterable[int]) -> None:
        self.conn.executemany(
            "INSERT INTO person_group (person_id, group_id) VALUES (?, ?)",
            ((person_id, group_id) for group_id in group_ids),
        )


class StatsRepository:
    """Store computed stats payloads."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, payload: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO stats (payload) VALUES (?)",
            (payload,),
        )
        return int(cursor.lastrowid)


class AuditLogRepository:
    """Write audit entries for user actions."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        action: str,
        entity_type: str,
        details: str,
        entity_id: int | None = None,
        actor: str | None = None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO audit_log (action, entity_type, details, entity_id, actor)
            VALUES (?, ?, ?, ?, ?)
            """,
            (action, entity_type, details, entity_id, actor),
        )
        return int(cursor.lastrowid)
