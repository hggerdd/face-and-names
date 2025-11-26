from __future__ import annotations

from pathlib import Path

from face_and_names.models.db import initialize_database
from face_and_names.services.people_service import PeopleService
from face_and_names.services.person_registry import PersonRegistry, default_registry_path


def _insert_import_and_image(conn, db_root: Path) -> int:
    conn.execute("INSERT INTO import_session (folder_count, image_count) VALUES (?, ?)", (1, 0))
    import_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
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
            "photos/img.jpg",
            "photos",
            "img.jpg",
            b"\x00" * 32,
            1,
            10,
            10,
            1,
            0,
            b"\x00\x01",
            123,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_create_person_adds_aliases(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    registry_path = default_registry_path(tmp_path)
    service = PeopleService(conn, registry_path=registry_path)

    pid = service.create_person("Alice", "Doe", short_name="Ali", aliases=["Al", "A"])
    people = service.list_people()

    assert pid > 0
    assert people[0]["display_name"] == "Ali"
    assert {"name": "Al", "kind": "alias"} in people[0]["aliases"]
    # Registry persisted to disk
    reg = PersonRegistry(registry_path)
    assert reg.get(pid).primary_name == "Ali"


def test_merge_people_rebinds_faces_and_aliases(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    img_id = _insert_import_and_image(conn, tmp_path)
    registry_path = default_registry_path(tmp_path)
    service = PeopleService(conn, registry_path=registry_path)

    source = service.create_person("Person", "One", aliases=["P1"])
    target = service.create_person("Person", "Two", aliases=["P2"])
    group_id = service.create_group("Family")
    service.assign_groups(source, [group_id])
    conn.execute(
        """
        INSERT INTO face (
            image_id, bbox_x, bbox_y, bbox_w, bbox_h,
            bbox_rel_x, bbox_rel_y, bbox_rel_w, bbox_rel_h,
            face_crop_blob, cluster_id, person_id, predicted_person_id,
            prediction_confidence, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            img_id,
            1.0,
            1.0,
            2.0,
            2.0,
            0.1,
            0.1,
            0.2,
            0.2,
            b"\x00\x01",
            None,
            source,
            source,
            0.9,
            "manual",
        ),
    )
    conn.commit()

    service.merge_people([source], target_id=target)

    face_row = conn.execute("SELECT person_id, predicted_person_id FROM face").fetchone()
    assert face_row == (target, target)

    aliases = conn.execute(
        "SELECT name FROM person_alias WHERE person_id = ?", (target,)
    ).fetchall()
    alias_names = {row[0] for row in aliases}
    assert "P1" in alias_names

    memberships = conn.execute(
        "SELECT COUNT(*) FROM person_group WHERE person_id = ?", (target,)
    ).fetchone()[0]
    assert memberships == 1

    row = conn.execute("SELECT 1 FROM person WHERE id = ?", (source,)).fetchone()
    assert row is None


def test_rename_person_updates_name(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    registry_path = default_registry_path(tmp_path)
    service = PeopleService(conn, registry_path=registry_path)

    pid = service.create_person("Old", "Name")
    service.rename_person(pid, "New", "Name", short_name="NN")

    row = conn.execute(
        "SELECT primary_name, short_name FROM person WHERE id = ?", (pid,)
    ).fetchone()
    assert row[0] == "NN"
    assert row[1] == "NN"
