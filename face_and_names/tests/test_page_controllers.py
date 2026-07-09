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
from face_and_names.services.clustering_page_controller import ClusteringPageController
from face_and_names.services.people_groups_controller import PeopleGroupsController
from face_and_names.services.people_service import PeopleService
from face_and_names.services.person_registry import default_registry_path
from face_and_names.services.prediction_review_controller import (
    PredictionReviewController,
    PredictionReviewFilters,
)


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    return initialize_database(tmp_path / "faces.db")


@pytest.fixture()
def people_service(conn: sqlite3.Connection, tmp_path: Path) -> PeopleService:
    return PeopleService(conn, registry_path=default_registry_path(tmp_path))


def _seed_image_with_face(
    conn: sqlite3.Connection,
    *,
    person_id: int | None = None,
    predicted_person_id: int | None = None,
    prediction_confidence: float | None = None,
    cluster_id: int | None = None,
    filename: str = "img.jpg",
    hash_byte: int = 0x11,
    metadata_date: str | None = None,
) -> tuple[int, int]:
    session_id = ImportSessionRepository(conn).create(folder_count=1)
    image_id = ImageRepository(conn).add(
        import_id=session_id,
        relative_path=f"family/{filename}",
        sub_folder="family",
        filename=filename,
        content_hash=bytes([hash_byte]) * 32,
        perceptual_hash=hash_byte,
        width=300,
        height=200,
        orientation_applied=1,
        has_faces=1,
        thumbnail_blob=b"thumb",
        size_bytes=4096,
    )
    face_id = FaceRepository(conn).add(
        image_id=image_id,
        bbox_abs=(10.0, 20.0, 50.0, 60.0),
        bbox_rel=(0.1, 0.2, 0.5, 0.6),
        face_crop_blob=b"face",
        provenance="detected",
        cluster_id=cluster_id,
        person_id=person_id,
        predicted_person_id=predicted_person_id,
        prediction_confidence=prediction_confidence,
    )
    if metadata_date:
        conn.execute(
            "INSERT INTO metadata (image_id, key, type, value) VALUES (?, ?, ?, ?)",
            (image_id, "DateTimeOriginal", "str", metadata_date),
        )
    conn.commit()
    return image_id, face_id


def test_prediction_review_controller_filters_and_accepts_predictions(
    conn: sqlite3.Connection, people_service: PeopleService, tmp_path: Path
) -> None:
    person_id = people_service.create_person("Ada", "Lovelace")
    _, face_id = _seed_image_with_face(
        conn,
        predicted_person_id=person_id,
        prediction_confidence=0.92,
    )
    _seed_image_with_face(
        conn,
        filename="low.jpg",
        hash_byte=0x12,
        predicted_person_id=person_id,
        prediction_confidence=0.2,
    )
    controller = PredictionReviewController(conn, tmp_path)

    filters = PredictionReviewFilters(
        predicted_person_id=person_id,
        confidence_min=0.8,
        confidence_max=1.0,
        unnamed_only=True,
    )

    assert controller.predicted_counts() == {person_id: 2}
    assert controller.count_faces(filters) == 1
    assert controller.load_faces(filters, limit=10, offset=0)[0].face_id == face_id
    assert controller.accept_predictions([face_id]) == 1
    assert conn.execute("SELECT person_id FROM face WHERE id = ?", (face_id,)).fetchone() == (
        person_id,
    )


def test_clustering_page_controller_assigns_batch_and_resolves_original(
    conn: sqlite3.Connection, people_service: PeopleService, tmp_path: Path
) -> None:
    person_id = people_service.create_person("Grace", "Hopper")
    _, first_face_id = _seed_image_with_face(conn, cluster_id=4)
    _, second_face_id = _seed_image_with_face(conn, filename="b.jpg", hash_byte=0x13, cluster_id=4)
    controller = ClusteringPageController(conn, tmp_path)

    assert controller.list_folders() == ["family"]
    assert controller.assign_person_to_faces([first_face_id, second_face_id], person_id) == 2
    assert controller.face_record(first_face_id).person_id == person_id  # type: ignore[union-attr]
    original = controller.get_original_face_image(first_face_id)
    assert original is not None
    assert original.image_path == tmp_path / "family" / "img.jpg"
    assert original.bbox_rel == (0.1, 0.2, 0.5, 0.6)


def test_people_groups_controller_counts_fetches_and_filters_by_photo_date(
    conn: sqlite3.Connection, people_service: PeopleService, tmp_path: Path
) -> None:
    person_id = people_service.create_person("Katherine", "Johnson")
    _, first_face_id = _seed_image_with_face(
        conn,
        person_id=person_id,
        filename="old.jpg",
        hash_byte=0x21,
        metadata_date="2020:01:02 10:00:00",
    )
    _seed_image_with_face(
        conn,
        person_id=person_id,
        filename="new.jpg",
        hash_byte=0x22,
        metadata_date="2022:03:04 10:00:00",
    )
    controller = PeopleGroupsController(conn, tmp_path)

    assert controller.count_faces(person_id) == 2
    assert controller.count_images(person_id) == 2
    assert [row.face_id for row in controller.fetch_faces(person_id, 10, 0, "date_asc")] == [
        first_face_id,
        first_face_id + 1,
    ]

    filtered = controller.fetch_images(
        person_id,
        limit=10,
        offset=0,
        sort_key="date_desc",
        start=PeopleGroupsController.parse_date("2022-01-01"),
        end=PeopleGroupsController.parse_date("2022-12-31"),
    )

    assert len(filtered) == 1
    assert filtered[0].relative_path == "family/new.jpg"
    assert controller.shot_date_for_face(first_face_id).date().isoformat() == "2020-01-02"
