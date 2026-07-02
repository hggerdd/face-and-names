from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from face_and_names.models.db import initialize_database
from face_and_names.models.repositories import (
    FaceRepository,
    ImageRepository,
    ImportSessionRepository,
)
from face_and_names.services.faces_workspace_controller import FacesWorkspaceController
from face_and_names.services.people_service import PeopleService
from face_and_names.services.person_registry import default_registry_path


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    return initialize_database(tmp_path / "faces.db")


@pytest.fixture()
def people_service(conn: sqlite3.Connection, tmp_path: Path) -> PeopleService:
    return PeopleService(conn, registry_path=default_registry_path(tmp_path))


@pytest.fixture()
def controller(
    conn: sqlite3.Connection, tmp_path: Path, people_service: PeopleService
) -> FacesWorkspaceController:
    return FacesWorkspaceController(conn, tmp_path, people_service)


def _seed_image_with_face(
    conn: sqlite3.Connection, person_id: int | None = None
) -> tuple[int, int]:
    sessions = ImportSessionRepository(conn)
    images = ImageRepository(conn)
    faces = FaceRepository(conn)
    session_id = sessions.create(folder_count=1)
    image_id = images.add(
        import_id=session_id,
        relative_path="family/img.jpg",
        sub_folder="family",
        filename="img.jpg",
        content_hash=b"\x11" * 32,
        perceptual_hash=111,
        width=300,
        height=300,
        orientation_applied=1,
        has_faces=1,
        thumbnail_blob=b"thumb",
        size_bytes=8192,
    )
    face_id = faces.add(
        image_id=image_id,
        bbox_abs=(1.0, 2.0, 50.0, 60.0),
        bbox_rel=(0.01, 0.02, 0.5, 0.6),
        face_crop_blob=b"face",
        provenance="detected",
        person_id=person_id,
        prediction_confidence=None,
    )
    conn.commit()
    return image_id, face_id


def test_faces_workspace_controller_loads_folder_image_and_face_data(
    conn: sqlite3.Connection,
    controller: FacesWorkspaceController,
) -> None:
    image_id, _ = _seed_image_with_face(conn)

    assert controller.list_folders() == ["family"]

    images, total = controller.load_images("family", offset=0, limit=10)
    assert total == 1
    assert images[0].image_id == image_id
    assert images[0].filename == "img.jpg"

    assert controller.load_face_boxes(image_id) == [(0.01, 0.02, 0.5, 0.6)]
    assert controller.load_face_tiles(image_id)[0].crop == b"face"
    assert controller.load_face_table_rows(image_id)[0].person_name == ""


def test_faces_workspace_controller_assigns_person_and_resolves_original(
    conn: sqlite3.Connection,
    controller: FacesWorkspaceController,
    people_service: PeopleService,
    tmp_path: Path,
) -> None:
    _, face_id = _seed_image_with_face(conn)
    person_id = people_service.create_person("Ada", "Lovelace")

    controller.assign_person(face_id, person_id)

    row = conn.execute("SELECT person_id FROM face WHERE id = ?", (face_id,)).fetchone()
    assert row == (person_id,)

    original = controller.get_original_face_image(face_id)
    assert original is not None
    assert original.image_path == tmp_path / "family" / "img.jpg"
    assert original.bbox_rel == (0.01, 0.02, 0.5, 0.6)
