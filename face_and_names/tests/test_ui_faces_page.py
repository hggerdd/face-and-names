from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

import pytest
from PyQt6.QtCore import Qt

from face_and_names.app_context import AppContext, EventBus
from face_and_names.models.db import initialize_database
from face_and_names.models.repositories import (
    FaceRepository,
    ImageRepository,
    ImportSessionRepository,
)
from face_and_names.services.person_registry import default_registry_path
from face_and_names.ui.faces_page import FacesPage


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "faces.db"


@pytest.fixture
def conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    connection = initialize_database(db_path)
    yield connection
    connection.close()


@pytest.fixture
def context(conn: sqlite3.Connection, db_path: Path) -> AppContext:
    from face_and_names.services.people_service import PeopleService
    from face_and_names.services.workers import JobManager

    job_manager = JobManager(max_workers=1)
    registry_path = default_registry_path(db_path.parent)
    people_service = PeopleService(conn, registry_path=registry_path)

    return AppContext(
        config={},
        db_path=db_path,
        conn=conn,
        config_path=db_path.parent / "config.toml",
        job_manager=job_manager,
        events=EventBus(),
        people_service=people_service,
        registry_path=registry_path,
        prediction_service=None,
    )


@pytest.fixture
def faces_page(context: AppContext, qtbot) -> FacesPage:
    page = FacesPage(context)
    qtbot.addWidget(page)
    return page


def _seed_faces(
    conn: sqlite3.Connection,
    folder: str,
    count: int,
    *,
    predicted_person_id: int | None = None,
) -> list[int]:
    sessions = ImportSessionRepository(conn)
    images = ImageRepository(conn)
    faces = FaceRepository(conn)
    session_id = sessions.create(1)
    face_ids: list[int] = []
    existing_count = int(conn.execute("SELECT COUNT(*) FROM image").fetchone()[0])
    for index in range(count):
        unique_index = existing_count + index + 1
        image_id = images.add(
            import_id=session_id,
            relative_path=f"{folder}/img{index}.jpg",
            sub_folder=folder,
            filename=f"img{index}.jpg",
            content_hash=bytes([unique_index]) * 32,
            perceptual_hash=unique_index,
            width=100,
            height=100,
            orientation_applied=1,
            has_faces=1,
            thumbnail_blob=b"thumb",
            size_bytes=100,
        )
        face_id = faces.add(
            image_id=image_id,
            bbox_abs=(1.0, 2.0, 10.0, 12.0),
            bbox_rel=(0.01, 0.02, 0.1, 0.12),
            face_crop_blob=b"face",
            provenance="detected",
            person_id=None,
            predicted_person_id=predicted_person_id,
            prediction_confidence=0.8 if predicted_person_id is not None else None,
        )
        face_ids.append(face_id)
    conn.commit()
    return face_ids


def test_faces_page_loads_folder_scope(faces_page: FacesPage, conn: sqlite3.Connection) -> None:
    _seed_faces(conn, "vacation", 1)
    _seed_faces(conn, "work", 1)

    faces_page.refresh_data()

    root = faces_page.tree.topLevelItem(0)
    assert root.text(0) == "All folders"
    children = [root.child(i).text(0) for i in range(root.childCount())]
    assert "vacation" in children
    assert "work" in children


def test_faces_page_loads_face_grid_for_selected_scope(
    faces_page: FacesPage, conn: sqlite3.Connection
) -> None:
    _seed_faces(conn, "vacation", 3)
    faces_page.refresh_data()

    root = faces_page.tree.topLevelItem(0)
    faces_page.tree.setCurrentItem(root.child(0))

    assert len(faces_page.current_tiles) == 3
    assert faces_page.total_faces == 3
    assert faces_page.selection_label.text() == "3 selected"


def test_faces_page_face_grid_paging(
    faces_page: FacesPage, conn: sqlite3.Connection, qtbot
) -> None:
    faces_page.PAGE_SIZE = 2
    _seed_faces(conn, "huge", 5)
    faces_page.refresh_data()

    root = faces_page.tree.topLevelItem(0)
    faces_page.tree.setCurrentItem(root.child(0))

    assert len(faces_page.current_tiles) == 2
    assert faces_page.next_btn.isEnabled()

    qtbot.mouseClick(faces_page.next_btn, Qt.MouseButton.LeftButton)

    assert len(faces_page.current_tiles) == 2
    assert faces_page.page_label.text() == "Page 2/3"


def test_faces_page_mode_filter_limits_face_grid(
    faces_page: FacesPage, conn: sqlite3.Connection, context: AppContext
) -> None:
    person_id = context.people_service.create_person("Ada", "Lovelace")
    _seed_faces(conn, "pics", 1)
    _seed_faces(conn, "pics", 1, predicted_person_id=person_id)
    faces_page.refresh_data()

    root = faces_page.tree.topLevelItem(0)
    faces_page.tree.setCurrentItem(root.child(0))
    assert faces_page.total_faces == 2

    faces_page.mode_combo.setCurrentIndex(2)

    assert faces_page.mode_combo.currentData() == "predicted"
    assert faces_page.total_faces == 1
    assert len(faces_page.current_tiles) == 1


def test_faces_page_accepts_selected_predictions(
    faces_page: FacesPage,
    conn: sqlite3.Connection,
    context: AppContext,
) -> None:
    person_id = context.people_service.create_person("Ada", "Lovelace")
    face_ids = _seed_faces(conn, "pics", 1, predicted_person_id=person_id)
    faces_page.refresh_data()

    faces_page._accept_selected_predictions()

    row = conn.execute("SELECT person_id FROM face WHERE id = ?", (face_ids[0],)).fetchone()
    assert row == (person_id,)
