from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from face_and_names.models.db import SCHEMA_VERSION, initialize_database
from face_and_names.models.repositories import FaceEmbeddingRepository
from face_and_names.services.embedding_service import VersionedEmbeddingService


def _table_names(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cursor.fetchall()}


def _insert_import_session(conn: sqlite3.Connection) -> int:
    conn.execute("INSERT INTO import_session (folder_count, image_count) VALUES (?, ?)", (1, 0))
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
            face_crop_blob, face_detection_index, cluster_id, person_id, predicted_person_id,
            prediction_confidence, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            b"\x00\x01",
            0.9,
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
        "schema_version",
        "import_session",
        "image",
        "metadata",
        "face",
        "face_embedding",
        "person",
        "person_alias",
        "group",
        "person_group",
        "stats",
        "audit_log",
    }

    assert expected.issubset(tables)


def test_schema_version_written(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    version = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()[0]
    assert version == SCHEMA_VERSION


def test_migration_from_v2_adds_face_embedding_table(tmp_path: Path) -> None:
    db_path = tmp_path / "faces.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE schema_version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)"
    )
    conn.execute("INSERT INTO schema_version (id, version) VALUES (1, 2)")
    conn.execute("CREATE TABLE face (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    migrated = initialize_database(db_path)

    assert "face_embedding" in _table_names(migrated)
    assert (
        migrated.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()[0]
        == SCHEMA_VERSION
    )


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


def test_face_embedding_rows_are_versioned_and_cascade_with_face(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    import_id = _insert_import_session(conn)
    image_id = _insert_image(conn, import_id, b"\x02" * 32)
    _insert_face(conn, image_id)
    face_id = int(conn.execute("SELECT id FROM face").fetchone()[0])
    crop = b"crop-bytes"
    repo = FaceEmbeddingRepository(conn)

    repo.upsert(
        face_id=face_id,
        model_name="test-model",
        model_version="v1",
        crop_sha256=VersionedEmbeddingService.crop_sha256(crop),
        vector_dim=3,
        vector_dtype="float32",
        vector_blob=b"\x00" * 12,
    )
    conn.commit()

    record = repo.get(
        face_id=face_id,
        model_name="test-model",
        model_version="v1",
        crop_sha256=VersionedEmbeddingService.crop_sha256(crop),
    )
    assert record is not None
    assert record.vector_dim == 3

    conn.execute("DELETE FROM face WHERE id = ?", (face_id,))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM face_embedding").fetchone()[0] == 0
