from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

import pytest
from PyQt6.QtCore import Qt

from face_and_names.app_context import AppContext, EventBus
from face_and_names.models.db import initialize_database
from face_and_names.models.repositories import ImageRepository, ImportSessionRepository
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
    
    # Mock job manager
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


def _seed_images(conn: sqlite3.Connection, folder: str, count: int) -> None:
    sessions = ImportSessionRepository(conn)
    images = ImageRepository(conn)
    sid = sessions.create(1)
    # Minimal valid JPEG
    valid_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00\x00?\x00\xbe\x80\xff\xd9"
    
    import hashlib
    base_hash = hashlib.sha256(folder.encode()).digest()
    
    for i in range(count):
        # Mix folder hash with index to guarantee uniqueness across folders
        mixed = bytearray(base_hash)
        mixed[0] = (mixed[0] + i) % 256
        
        images.add(
            import_id=sid,
            relative_path=f"{folder}/img{i}.jpg",
            sub_folder=folder,
            filename=f"img{i}.jpg",
            content_hash=bytes(mixed),
            perceptual_hash=i,
            width=100,
            height=100,
            orientation_applied=1,
            has_faces=0,
            thumbnail_blob=valid_jpg,
            size_bytes=100,
        )
    conn.commit()


def test_faces_page_loads_folders(faces_page: FacesPage, conn: sqlite3.Connection, qtbot) -> None:
    _seed_images(conn, "vacation", 1)
    _seed_images(conn, "work", 1)
    
    faces_page.refresh_data()
    
    root = faces_page.tree.topLevelItem(0)
    assert root.text(0) == "/"
    
    # Check children
    children = [root.child(i).text(0) for i in range(root.childCount())]
    assert "vacation" in children
    assert "work" in children


def test_faces_page_selecting_folder_loads_images(faces_page: FacesPage, conn: sqlite3.Connection, qtbot) -> None:
    _seed_images(conn, "vacation", 5)
    faces_page.refresh_data()
    
    # Find and select 'vacation'
    root = faces_page.tree.topLevelItem(0)
    vacation_item = None
    for i in range(root.childCount()):
        if root.child(i).text(0) == "vacation":
            vacation_item = root.child(i)
            break
    
    assert vacation_item is not None
    faces_page.tree.setCurrentItem(vacation_item)
    
    # Wait for signals if async, but here it's sync
    assert faces_page.image_list.count() == 5
    assert faces_page.status.text().startswith("5/5 images")


def test_faces_page_paging(faces_page: FacesPage, conn: sqlite3.Connection, qtbot) -> None:
    faces_page.page_size = 2
    _seed_images(conn, "huge", 5)
    faces_page.refresh_data()
    
    # Select folder
    root = faces_page.tree.topLevelItem(0)
    faces_page.tree.setCurrentItem(root.child(0))
    
    assert faces_page.image_list.count() == 2
    assert faces_page.load_more_btn.isEnabled()
    
    # Click load more
    qtbot.mouseClick(faces_page.load_more_btn, Qt.MouseButton.LeftButton)
    
    assert faces_page.image_list.count() == 4
    assert faces_page.load_more_btn.isEnabled()
    
    # Click load more again (last item)
    qtbot.mouseClick(faces_page.load_more_btn, Qt.MouseButton.LeftButton)
    
    assert faces_page.image_list.count() == 5
    assert not faces_page.load_more_btn.isEnabled()


def test_faces_page_selecting_image_shows_preview(faces_page: FacesPage, conn: sqlite3.Connection, qtbot) -> None:
    _seed_images(conn, "pics", 1)
    faces_page.refresh_data()
    
    # Select folder
    root = faces_page.tree.topLevelItem(0)
    faces_page.tree.setCurrentItem(root.child(0))
    
    # Select image
    faces_page.image_list.setCurrentRow(0)
    
    # Check preview scene has items
    assert len(faces_page.preview.scene().items()) > 0
    assert "0 faces" in faces_page.status.text()
