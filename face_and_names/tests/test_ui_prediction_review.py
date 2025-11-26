from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt

from face_and_names.app_context import AppContext
from face_and_names.ui.prediction_review_page import PredictionReviewPage


@pytest.fixture
def mock_context():
    conn = sqlite3.connect(":memory:")
    # Setup schema needed for queries
    conn.execute(
        "CREATE TABLE person (id INTEGER PRIMARY KEY, primary_name TEXT, first_name TEXT, last_name TEXT, short_name TEXT, display_name TEXT, birthdate TEXT, notes TEXT)"
    )
    conn.execute("CREATE TABLE person_alias (person_id INTEGER, name TEXT, kind TEXT)")
    conn.execute("""
        CREATE TABLE face (
            id INTEGER PRIMARY KEY,
            person_id INTEGER,
            predicted_person_id INTEGER,
            prediction_confidence REAL,
            face_crop_blob BLOB,
            image_id INTEGER,
            bbox_x REAL, bbox_y REAL, bbox_w REAL, bbox_h REAL,
            bbox_rel_x REAL, bbox_rel_y REAL, bbox_rel_w REAL, bbox_rel_h REAL,
            provenance TEXT
        )
    """)

    # Seed data: 25 faces for predicted_person_id=1
    conn.execute("INSERT INTO person (id, primary_name) VALUES (1, 'Alice')")
    for i in range(25):
        conn.execute(
            """
            INSERT INTO face (
                predicted_person_id, prediction_confidence, face_crop_blob, provenance,
                bbox_x, bbox_y, bbox_w, bbox_h, bbox_rel_x, bbox_rel_y, bbox_rel_w, bbox_rel_h
            ) VALUES (1, 0.9, ?, 'predicted', 0,0,0,0,0,0,0,0)
            """,
            (b"fake",),
        )
    conn.commit()

    context = MagicMock(spec=AppContext)
    context.conn = conn
    context.db_path = MagicMock()
    context.people_service = MagicMock()
    return context


def test_pagination_logic(qtbot, mock_context):
    page = PredictionReviewPage(mock_context)
    qtbot.addWidget(page)

    # Select person 1
    # We need to mock people_service.list_people to return Alice
    page.people_service.list_people = MagicMock(return_value=[{"id": 1, "primary_name": "Alice"}])
    page.refresh_data()

    # Select Alice in list
    item = page.people_list.item(0)
    page.people_list.setCurrentItem(item)

    # Should show first 20 items
    assert len(page.current_tiles) == 20
    assert page.current_page == 0
    assert page.page_label.text() == "1/2"
    assert page.prev_btn.isEnabled() is False
    assert page.next_btn.isEnabled() is True

    # Go to next page
    qtbot.mouseClick(page.next_btn, Qt.MouseButton.LeftButton)

    # Should show remaining 5 items
    assert len(page.current_tiles) == 5
    assert page.current_page == 1
    assert page.page_label.text() == "2/2"
    assert page.prev_btn.isEnabled() is True
    assert page.next_btn.isEnabled() is False

    # Go back
    qtbot.mouseClick(page.prev_btn, Qt.MouseButton.LeftButton)
    assert len(page.current_tiles) == 20
    assert page.current_page == 0


def test_filter_resets_pagination(qtbot, mock_context):
    page = PredictionReviewPage(mock_context)
    qtbot.addWidget(page)

    page.people_service.list_people = MagicMock(return_value=[{"id": 1, "primary_name": "Alice"}])
    page.refresh_data()
    page.people_list.setCurrentRow(0)

    # Go to page 2
    page._next_page()
    assert page.current_page == 1

    # Change filter
    page.min_conf.setValue(0.5)

    # Should reset to page 1
    assert page.current_page == 0
    assert page.page_label.text() == "1/2"


def test_deletion_updates_pagination(qtbot, mock_context):
    page = PredictionReviewPage(mock_context)
    qtbot.addWidget(page)

    page.people_service.list_people = MagicMock(return_value=[{"id": 1, "primary_name": "Alice"}])
    page.refresh_data()
    page.people_list.setCurrentRow(0)

    # Initial state: 25 items -> 2 pages
    assert page.page_label.text() == "1/2"

    # Mock deletion: delete 6 items from DB
    # We need to manually update the mock DB because the UI calls delete on repo which commits
    # But our mock_context has an in-memory DB.
    # The UI calls self.face_repo.delete(face_id).
    # We can just manually delete from the DB since the UI reloads from DB.

    # Delete 6 faces
    mock_context.conn.execute("DELETE FROM face WHERE id IN (SELECT id FROM face LIMIT 6)")
    mock_context.conn.commit()

    # Trigger reload (simulate delete callback)
    page._load_faces()

    # Now 19 items -> 1 page
    assert page.page_label.text() == "1/1"
    assert page.next_btn.isEnabled() is False
