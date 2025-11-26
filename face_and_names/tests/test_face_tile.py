from __future__ import annotations

import os
from io import BytesIO

import pytest
from PIL import Image
from PyQt6.QtWidgets import QApplication

from face_and_names.ui.components.face_tile import FaceTile, FaceTileData

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# UI-heavy tests are skipped in environments where headless Qt can hang; adjust when GUI testing infra is available.
pytest.skip("Skipping FaceTile UI interaction tests in headless/offscreen mode", allow_module_level=True)


def _make_crop_bytes(color: str = "red", size: tuple[int, int] = (48, 48)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_face_tile_selection_toggle():
    _app()
    data = FaceTileData(
        face_id=1,
        person_id=None,
        person_name=None,
        predicted_person_id=None,
        predicted_name=None,
        confidence=None,
        crop=_make_crop_bytes(),
    )
    changed: list[tuple[int, bool]] = []

    tile = FaceTile(
        data,
        delete_face=lambda fid: None,
        assign_person=lambda fid, pid: None,
        list_persons=lambda: [],
        create_person=lambda name: 0,
        rename_person=lambda pid, name: None,
    )
    tile.selectionChanged.connect(lambda fid, sel: changed.append((fid, sel)))

    assert tile.is_selected() is True
    tile.toggle_selected()
    assert tile.is_selected() is False
    assert changed and changed[-1] == (1, False)


def test_assign_predicted_updates_person():
    _app()
    assigned: list[tuple[int, int | None]] = []

    def assign_person(fid: int, pid: int | None) -> None:
        assigned.append((fid, pid))

    data = FaceTileData(
        face_id=2,
        person_id=None,
        person_name=None,
        predicted_person_id=5,
        predicted_name="Pred Name",
        confidence=0.9,
        crop=_make_crop_bytes("blue"),
    )

    tile = FaceTile(
        data,
        delete_face=lambda fid: None,
        assign_person=assign_person,
        list_persons=lambda: [],
        create_person=lambda name: 0,
        rename_person=lambda pid, name: None,
    )
    tile._assign_predicted()

    assert assigned == [(2, 5)]
    assert tile.data.person_id == 5
    assert tile.assigned_label.text() == "Pred Name"
