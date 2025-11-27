"""
People & Groups page (people list + assigned faces with pagination).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from face_and_names.services.people_service import PeopleService
from face_and_names.ui.components.face_tile import FaceTile, FaceTileData
from face_and_names.ui.faces_page import FaceImageView


@dataclass
class FaceRow:
    face_id: int
    person_id: int | None
    person_name: str | None
    predicted_person_id: int | None
    predicted_name: str | None
    confidence: float | None
    crop: bytes


def _person_label(person: dict) -> str:
    first = (person.get("first_name") or "").strip()
    last = (person.get("last_name") or "").strip()
    short = (person.get("short_name") or "").strip()
    parts = []
    if short:
        parts.append(f"Short: {short}")
    if first or last:
        parts.append(f"Name: {first} {last}".strip())
    display = person.get("display_name") or person.get("primary_name") or ""
    parts.append(f"Display: {display}")
    return " | ".join(parts)


def _person_sort_key(person: dict) -> str:
    return (
        person.get("short_name") or person.get("display_name") or person.get("primary_name") or ""
    ).casefold()


SORT_OPTIONS = {
    "date_desc": ("Photo date: latest first", "COALESCE(m.value, '') DESC, f.id DESC"),
    "date_asc": ("Photo date: oldest first", "COALESCE(m.value, '') ASC, f.id ASC"),
}

VIEW_MODE_FACES = "faces"
VIEW_MODE_IMAGES = "images"


class PeopleGroupsPage(QWidget):
    """People page showing a sortable list of people and their faces."""

    PAGE_SIZE = 20

    def __init__(
        self,
        service_provider: Callable[[], PeopleService | None],
        *,
        confirm_delete: bool = True,
        db_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_provider = service_provider
        self.confirm_delete = confirm_delete
        self.db_path = db_path
        self.people_list = QListWidget()
        self.people_list.setMinimumWidth(260)
        self.faces_area = QScrollArea()
        self.faces_area.setWidgetResizable(True)
        self.faces_inner = QWidget()
        self.faces_layout = QGridLayout()
        self.faces_layout.setContentsMargins(8, 8, 8, 8)
        self.faces_layout.setSpacing(12)
        self.faces_inner.setLayout(self.faces_layout)
        self.faces_area.setWidget(self.faces_inner)
        self.status = QLabel("Select a person to view faces.")
        self.page_label = QLabel("Page 1/1")
        self.prev_btn = QPushButton("<")
        self.next_btn = QPushButton(">")
        self.sort_combo = QComboBox()
        for key, (label, _) in SORT_OPTIONS.items():
            self.sort_combo.addItem(label, userData=key)
        self.sort_combo.setCurrentIndex(0)
        self.faces_mode_btn = QRadioButton("Faces")
        self.images_mode_btn = QRadioButton("Complete images")
        self.faces_mode_btn.setChecked(True)
        self.people: list[dict] = []
        self.current_person_id: int | None = None
        self.current_page = 0
        self.current_tiles: list[FaceTile] = []
        self.sort_key = self.sort_combo.currentData()
        self.view_mode = VIEW_MODE_FACES

        self._build_ui()
        self._refresh_people()

    def _service(self) -> PeopleService | None:
        return self._service_provider()

    def _build_ui(self) -> None:
        left = QVBoxLayout()
        left.addWidget(QLabel("People (sorted by short/display name)"))
        left.addWidget(self.people_list, stretch=1)

        faces_controls = QHBoxLayout()
        faces_controls.addStretch(1)
        faces_controls.addWidget(QLabel("View:"))
        faces_controls.addWidget(self.faces_mode_btn)
        faces_controls.addWidget(self.images_mode_btn)
        faces_controls.addWidget(QLabel("Sort:"))
        faces_controls.addWidget(self.sort_combo)
        faces_controls.addWidget(self.prev_btn)
        faces_controls.addWidget(self.page_label)
        faces_controls.addWidget(self.next_btn)
        faces_controls.addStretch(1)

        right = QVBoxLayout()
        right.addLayout(faces_controls)
        right.addWidget(self.faces_area, stretch=1)
        right.addWidget(self.status)

        root = QHBoxLayout()
        root.addLayout(left, stretch=0)
        root.addLayout(right, stretch=1)
        self.setLayout(root)

        self.people_list.itemSelectionChanged.connect(self._on_person_selected)
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self.faces_mode_btn.toggled.connect(self._on_mode_changed)
        self.images_mode_btn.toggled.connect(self._on_mode_changed)

    def _refresh_people(self) -> None:
        service = self._service()
        if service is None:
            return
        try:
            people = service.list_people()
        except Exception:
            return
        people = sorted(people, key=_person_sort_key)
        self.people = people
        self.people_list.clear()
        for person in people:
            item = QListWidgetItem(_person_label(person))
            item.setData(Qt.ItemDataRole.UserRole, person.get("id"))
            self.people_list.addItem(item)
        if people:
            self.people_list.setCurrentRow(0)
        else:
            self._clear_faces()
            self.status.setText("No people found.")

    def showEvent(self, event) -> None:  # type: ignore[override]
        self._refresh_people()
        return super().showEvent(event)

    def _on_person_selected(self) -> None:
        items = self.people_list.selectedItems()
        self.current_person_id = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        self.current_page = 0
        self._load_faces()

    def _prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self._load_faces()

    def _next_page(self) -> None:
        self.current_page += 1
        self._load_faces()

    def _on_sort_changed(self) -> None:
        self.sort_key = self.sort_combo.currentData()
        self.current_page = 0
        self._load_faces()

    def _on_mode_changed(self) -> None:
        self.view_mode = VIEW_MODE_IMAGES if self.images_mode_btn.isChecked() else VIEW_MODE_FACES
        self.current_page = 0
        self._load_faces()

    def _clear_faces(self) -> None:
        self.current_tiles = []
        while self.faces_layout.count():
            item = self.faces_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _load_faces(self) -> None:
        self._clear_faces()
        person_id = self.current_person_id
        if person_id is None:
            self.status.setText("Select a person to view faces.")
            return
        if self.view_mode == VIEW_MODE_IMAGES:
            rows = self._fetch_images(
                person_id=person_id, limit=self.PAGE_SIZE, offset=self.current_page * self.PAGE_SIZE
            )
            total = self._count_images(person_id)
        else:
            rows = self._fetch_faces(
                person_id=person_id, limit=self.PAGE_SIZE, offset=self.current_page * self.PAGE_SIZE
            )
            total = self._count_faces(person_id)
        total_pages = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)
            if self.view_mode == VIEW_MODE_IMAGES:
                rows = self._fetch_images(
                    person_id=person_id,
                    limit=self.PAGE_SIZE,
                    offset=self.current_page * self.PAGE_SIZE,
                )
            else:
                rows = self._fetch_faces(
                    person_id=person_id,
                    limit=self.PAGE_SIZE,
                    offset=self.current_page * self.PAGE_SIZE,
                )
        self.page_label.setText(f"Page {self.current_page + 1}/{total_pages}")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)
        if not rows:
            self.status.setText("No faces assigned to this person.")
            return

        max_cols = 4
        for idx, row in enumerate(rows):
            service = self._service()
            if self.view_mode == VIEW_MODE_IMAGES:
                tile = self._build_image_tile(row, service)
            else:
                tile = self._build_face_tile(row, service)
            row_idx, col_idx = divmod(idx, max_cols)
            self.faces_layout.addWidget(tile, row_idx, col_idx, alignment=Qt.AlignmentFlag.AlignTop)
            self.current_tiles.append(tile)
        label = "faces" if self.view_mode == VIEW_MODE_FACES else "images"
        self.status.setText(f"Showing {len(rows)} {label} (Total: {total})")

    def _build_face_tile(self, row, service: PeopleService | None) -> FaceTile:
        return FaceTile(
            FaceTileData(
                face_id=row.face_id,
                person_id=row.person_id,
                person_name=row.person_name,
                predicted_person_id=row.predicted_person_id,
                predicted_name=row.predicted_name,
                confidence=row.confidence,
                crop=row.crop,
            ),
            delete_face=self._delete_face,
            assign_person=self._assign_person,
            list_persons=self._list_people,
            create_person=lambda first, last, short, service=service: service.create_person(  # type: ignore[arg-type,union-attr]
                first, last, short
            )
            if service
            else 0,
            rename_person=service.rename_person if service else lambda *_: None,  # type: ignore[arg-type]
            open_original=self._open_original_image,
            confirm_delete=self.confirm_delete,
        )

    def _build_image_tile(self, row, service: PeopleService | None) -> FaceTile:
        # Reuse FaceTile visuals but show the whole image thumb with no predicted info.
        return FaceTile(
            FaceTileData(
                face_id=row.face_id,  # image_id repurposed
                person_id=row.person_id,
                person_name=row.person_name,
                predicted_person_id=None,
                predicted_name=None,
                confidence=None,
                crop=row.thumb,
            ),
            delete_face=self._delete_image if service else lambda _: None,
            assign_person=lambda *_: None,
            list_persons=self._list_people,
            create_person=lambda *_: 0,
            rename_person=lambda *_: None,
            open_original=lambda *_: self._open_original_image_from_path(row.relative_path),
            confirm_delete=self.confirm_delete,
        )

    def _after_change(self) -> None:
        # Refresh faces and people counts when face data changes
        self._refresh_people()
        self._load_faces()

    def _delete_face(self, face_id: int) -> None:
        service = self._service()
        if service is None:
            return
        service.conn.execute("DELETE FROM face WHERE id = ?", (face_id,))
        service.conn.commit()

    def _delete_image(self, image_id: int) -> None:
        service = self._service()
        if service is None:
            return
        service.conn.execute("DELETE FROM image WHERE id = ?", (image_id,))
        service.conn.commit()

    def _assign_person(self, face_id: int, person_id: int | None) -> None:
        service = self._service()
        if service is None:
            return
        service.conn.execute("UPDATE face SET person_id = ? WHERE id = ?", (person_id, face_id))
        service.conn.commit()

    def _list_people(self) -> list[dict]:
        service = self._service()
        if service is None:
            return []
        return sorted(service.list_people(), key=_person_sort_key)

    def _count_faces(self, person_id: int) -> int:
        service = self._service()
        if service is None:
            return 0
        row = service.conn.execute(
            "SELECT COUNT(*) FROM face WHERE person_id = ?", (person_id,)
        ).fetchone()
        return int(row[0]) if row else 0

    def _count_images(self, person_id: int) -> int:
        service = self._service()
        if service is None:
            return 0
        row = service.conn.execute(
            """
            SELECT COUNT(DISTINCT f.image_id)
            FROM face f
            WHERE f.person_id = ?
            """,
            (person_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    def _fetch_faces(self, person_id: int, limit: int, offset: int) -> List[FaceRow]:
        service = self._service()
        if service is None:
            return []
        order_by = SORT_OPTIONS.get(self.sort_key or "date_desc", SORT_OPTIONS["date_desc"])[1]
        rows = service.conn.execute(
            """
            SELECT f.id, f.person_id, p.primary_name, f.predicted_person_id, pp.primary_name,
                   f.prediction_confidence, f.face_crop_blob
            FROM face f
            JOIN person p ON p.id = f.person_id
            LEFT JOIN person pp ON pp.id = f.predicted_person_id
            LEFT JOIN metadata m ON m.image_id = f.image_id AND m.key = 'DateTimeOriginal'
            WHERE f.person_id = ?
            ORDER BY """
            + order_by
            + """
            LIMIT ? OFFSET ?
            """,
            (person_id, limit, offset),
        ).fetchall()
        return [
            FaceRow(
                face_id=int(r[0]),
                person_id=r[1],
                person_name=r[2],
                predicted_person_id=r[3],
                predicted_name=r[4],
                confidence=r[5],
                crop=bytes(r[6]),
            )
            for r in rows
        ]

    def _fetch_images(self, person_id: int, limit: int, offset: int) -> List:
        service = self._service()
        if service is None:
            return []
        order_by = SORT_OPTIONS.get(self.sort_key or "date_desc", SORT_OPTIONS["date_desc"])[1]
        rows = service.conn.execute(
            """
            SELECT DISTINCT i.id, f.person_id, p.primary_name, i.thumbnail_blob, i.relative_path
            FROM face f
            JOIN image i ON i.id = f.image_id
            JOIN person p ON p.id = f.person_id
            LEFT JOIN metadata m ON m.image_id = f.image_id AND m.key = 'DateTimeOriginal'
            WHERE f.person_id = ?
            ORDER BY """  # noqa: COM812
            + order_by.replace("f.", "i.")
            + """
            LIMIT ? OFFSET ?
            """,
            (person_id, limit, offset),
        ).fetchall()
        return [
            type(
                "ImageRow",
                (),
                {
                    "face_id": r[0],
                    "person_id": r[1],
                    "person_name": r[2],
                    "thumb": bytes(r[3]),
                    "relative_path": r[4],
                    "predicted_person_id": None,
                    "predicted_name": None,
                    "confidence": None,
                },
            )  # simple struct-like
            for r in rows
        ]

    def _open_original_image(self, face_id: int) -> None:
        service = self._service()
        if service is None:
            return
        row = service.conn.execute(
            """
            SELECT f.id, f.image_id, f.bbox_rel_x, f.bbox_rel_y, f.bbox_rel_w, f.bbox_rel_h,
                   i.relative_path, i.width, i.height
            FROM face f
            JOIN image i ON i.id = f.image_id
            WHERE f.id = ?
            """,
            (face_id,),
        ).fetchone()
        if row is None:
            return
        _, image_id, x, y, w, h, rel_path, img_w, img_h = row
        base = self.db_path.parent if self.db_path else Path.cwd()
        img_path = base / rel_path
        if not img_path.exists():
            QMessageBox.warning(self, "Image missing", f"File not found: {img_path}")
            return
        from PyQt6.QtGui import QPixmap  # local import to avoid circular issues

        pix = QPixmap(str(img_path))
        window = QDialog(self)
        window.setWindowTitle("Original image")
        view = FaceImageView()
        view.show_image(pix, [(float(x), float(y), float(w), float(h))])
        layout = QVBoxLayout()
        layout.addWidget(view)
        window.setLayout(layout)
        window.resize(800, 600)
        window.exec()

    def _open_original_image_from_path(self, relative_path: str) -> None:
        base = self.db_path.parent if self.db_path else Path.cwd()
        img_path = base / relative_path
        if not img_path.exists():
            QMessageBox.warning(self, "Image missing", f"File not found: {img_path}")
            return
        from PyQt6.QtGui import QPixmap  # local import to avoid circular issues

        pix = QPixmap(str(img_path))
        window = QDialog(self)
        window.setWindowTitle("Original image")
        view = FaceImageView()
        view.show_image(pix, [])
        layout = QVBoxLayout()
        layout.addWidget(view)
        window.setLayout(layout)
        window.resize(800, 600)
        window.exec()
