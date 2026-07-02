from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from face_and_names.app_context import AppContext, EventBus
from face_and_names.models.db import initialize_database
from face_and_names.services.people_service import PeopleService
from face_and_names.services.person_registry import default_registry_path
from face_and_names.services.workers import JobManager
from face_and_names.ui.main_window import MainWindow


@pytest.fixture
def main_window_context(tmp_path: Path) -> AppContext:
    db_path = tmp_path / "faces.db"
    conn: sqlite3.Connection = initialize_database(db_path)
    registry_path = default_registry_path(tmp_path)
    people_service = PeopleService(conn, registry_path=registry_path)
    return AppContext(
        config={},
        config_path=tmp_path / "config.toml",
        db_path=db_path,
        conn=conn,
        job_manager=JobManager(max_workers=1),
        events=EventBus(),
        people_service=people_service,
        registry_path=registry_path,
        prediction_service=None,
    )


def test_main_window_starts_on_home_and_shows_implemented_diagnostics(
    main_window_context: AppContext, qtbot
) -> None:
    window = MainWindow(main_window_context)
    qtbot.addWidget(window)

    nav_items = [window.nav.item(row).text() for row in range(window.nav.count())]

    assert nav_items[0] == "Home"
    assert window.nav.currentItem().text() == "Home"
    assert "Diagnostics" in nav_items


def test_home_page_can_navigate_to_import(main_window_context: AppContext, qtbot) -> None:
    window = MainWindow(main_window_context)
    qtbot.addWidget(window)

    window._navigate_to("Import")

    assert window.nav.currentItem().text() == "Import"


def test_main_window_can_load_diagnostics_page(main_window_context: AppContext, qtbot) -> None:
    window = MainWindow(main_window_context)
    qtbot.addWidget(window)

    window._navigate_to("Diagnostics")

    assert window.nav.currentItem().text() == "Diagnostics"
    assert "Diagnostics" in window._pages
