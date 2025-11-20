from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from face_and_names.models.db import initialize_database


def _table_names(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cursor.fetchall()}


def _insert_import_session(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO import_session (folder_count, image_count) VALUES (?, ?)", (1, 0)
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _insert_image(
    conn: sqlite3.Connection,
    import_id: int,
    content_hash: bytes,
    perceptual_hash: int = 1,
    relative_path: str = "folder/img.jpg",
) -> int:
    conn.execute(
        """
        INSERT INTO image (
            import_id, relative_path, sub_folder, filename,
            content_hash, perceptual_hash, width, height,
            orientation_applied, has_faces, thumbnail_blob, size_bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_id,
            relative_path,
            "folder",
            "img.jpg",
            content_hash,
            perceptual_hash,
            100,
            100,
            1,
            0,
            b"\x00\x01",
            1234,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _insert_face(conn: sqlite3.Connection, image_id: int) -> None:
    conn.execute(
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
            1.0,
            2.0,
            50.0,
            60.0,
            0.01,
            0.02,
            0.5,
            0.6,
            "cache/faces/1.jpg",
            None,
            None,
            None,
            None,
            "detected",
        ),
    )


def test_initialize_creates_expected_tables(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")

    tables = _table_names(conn)
    expected = {
        "import_session",
        "image",
        "metadata",
        "face",
        "person",
        "person_alias",
        "group",
        "person_group",
        "stats",
        "audit_log",
    }

    assert expected.issubset(tables)


def test_unique_content_hash_enforced(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    import_id = _insert_import_session(conn)

    content_hash = b"\x00" * 32
    _insert_image(conn, import_id, content_hash)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_image(conn, import_id, content_hash, perceptual_hash=2, relative_path="other.jpg")


def test_cascade_delete_import_session_removes_child_records(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    import_id = _insert_import_session(conn)
    image_id = _insert_image(conn, import_id, b"\x01" * 32)
    _insert_face(conn, image_id)
    conn.commit()

    conn.execute("DELETE FROM import_session WHERE id = ?", (import_id,))
    conn.commit()

    image_count = conn.execute("SELECT COUNT(*) FROM image").fetchone()[0]
    face_count = conn.execute("SELECT COUNT(*) FROM face").fetchone()[0]

    assert image_count == 0
    assert face_count == 0
