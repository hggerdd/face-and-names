from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from face_and_names.models.db import initialize_database
from face_and_names.models.repositories import (
    AuditLogRepository,
    FaceRepository,
    GroupRepository,
    ImageRepository,
    ImportSessionRepository,
    MetadataRepository,
    PersonAliasRepository,
    PersonGroupRepository,
    PersonRepository,
    StatsRepository,
)


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    return initialize_database(tmp_path / "faces.db")


def test_import_session_increment(conn: sqlite3.Connection) -> None:
    repo = ImportSessionRepository(conn)

    session_id = repo.create(folder_count=3)
    repo.increment_image_count(session_id, delta=2)
    assert repo.get(session_id) == (session_id, 3, 2)


def test_image_repository_enforces_unique_content_hash(conn: sqlite3.Connection) -> None:
    sessions = ImportSessionRepository(conn)
    images = ImageRepository(conn)
    session_id = sessions.create(folder_count=1)

    content_hash = b"\x01" * 32
    images.add(
        import_id=session_id,
        relative_path="a/b.jpg",
        sub_folder="a",
        filename="b.jpg",
        content_hash=content_hash,
        perceptual_hash=123,
        width=100,
        height=100,
        orientation_applied=1,
        has_faces=0,
        thumbnail_blob=b"thumb",
        size_bytes=2048,
    )

    with pytest.raises(sqlite3.IntegrityError):
        images.add(
            import_id=session_id,
            relative_path="other/b.jpg",
            sub_folder="other",
            filename="b.jpg",
            content_hash=content_hash,
            perceptual_hash=124,
            width=50,
            height=50,
            orientation_applied=0,
            has_faces=0,
            thumbnail_blob=b"thumb2",
            size_bytes=1024,
        )


def test_metadata_repository_adds_entries(conn: sqlite3.Connection) -> None:
    sessions = ImportSessionRepository(conn)
    images = ImageRepository(conn)
    metadata = MetadataRepository(conn)
    session_id = sessions.create(folder_count=1)
    image_id = images.add(
        import_id=session_id,
        relative_path="a/img.jpg",
        sub_folder="a",
        filename="img.jpg",
        content_hash=b"\x02" * 32,
        perceptual_hash=222,
        width=200,
        height=100,
        orientation_applied=1,
        has_faces=0,
        thumbnail_blob=b"bytes",
        size_bytes=4096,
    )

    metadata.add_entries(image_id, {"Orientation": "6", "DateTimeOriginal": "2020:01:01"}, "EXIF")
    count = conn.execute("SELECT COUNT(*) FROM metadata WHERE image_id = ?", (image_id,)).fetchone()[0]
    assert count == 2


def test_face_repository_saves_faces(conn: sqlite3.Connection) -> None:
    sessions = ImportSessionRepository(conn)
    images = ImageRepository(conn)
    faces = FaceRepository(conn)
    session_id = sessions.create(folder_count=1)
    image_id = images.add(
        import_id=session_id,
        relative_path="a/img.jpg",
        sub_folder="a",
        filename="img.jpg",
        content_hash=b"\x03" * 32,
        perceptual_hash=333,
        width=300,
        height=300,
        orientation_applied=1,
        has_faces=1,
        thumbnail_blob=b"bytes",
        size_bytes=8192,
    )

    face_id = faces.add(
        image_id=image_id,
        bbox_abs=(1.0, 2.0, 50.0, 60.0),
        bbox_rel=(0.01, 0.02, 0.5, 0.6),
        face_crop_path="cache/faces/1.jpg",
        provenance="detected",
        cluster_id=None,
        person_id=None,
        predicted_person_id=None,
        prediction_confidence=None,
    )

    stored = conn.execute("SELECT id, image_id, provenance FROM face WHERE id = ?", (face_id,)).fetchone()
    assert stored == (face_id, image_id, "detected")


def test_people_groups_aliases_and_links(conn: sqlite3.Connection) -> None:
    people = PersonRepository(conn)
    aliases = PersonAliasRepository(conn)
    groups = GroupRepository(conn)
    person_groups = PersonGroupRepository(conn)

    person_id = people.create("Alice", birthdate="1990-01-01", notes="note")
    alias_id = aliases.add_alias(person_id, "Al")
    group_id = groups.create("Family", color="#ff0000")
    person_groups.add_memberships(person_id, [group_id])

    assert alias_id > 0
    linked = conn.execute(
        "SELECT person_id, group_id FROM person_group WHERE person_id = ? AND group_id = ?",
        (person_id, group_id),
    ).fetchone()
    assert linked == (person_id, group_id)


def test_stats_and_audit_repositories(conn: sqlite3.Connection) -> None:
    stats = StatsRepository(conn)
    audit = AuditLogRepository(conn)

    stats_id = stats.add('{"faces":10}')
    audit_id = audit.add(
        action="rename",
        entity_type="person",
        details='{"from":"Old","to":"New"}',
        entity_id=1,
        actor="tester",
    )

    saved_stats = conn.execute("SELECT payload FROM stats WHERE id = ?", (stats_id,)).fetchone()[0]
    saved_audit = conn.execute(
        "SELECT action, entity_type, actor FROM audit_log WHERE id = ?", (audit_id,)
    ).fetchone()

    assert saved_stats == '{"faces":10}'
    assert saved_audit == ("rename", "person", "tester")
