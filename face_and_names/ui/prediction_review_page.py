"""
Prediction Review page: fast verification of predicted names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QDialog,
)
from PyQt6.QtGui import QPixmap

from face_and_names.app_context import AppContext
from face_and_names.models.repositories import FaceRepository
from face_and_names.services.people_service import PeopleService
from face_and_names.ui.components.face_tile import FaceTile, FaceTileData
from face_and_names.ui.faces_page import FaceImageView


@dataclass
class FaceRow:
    face_id: int
    person_id: int | None
    predicted_person_id: int | None
    person_name: str | None
    predicted_name: str | None
    confidence: float | None
    crop: bytes


class PredictionReviewPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.people_service = PeopleService(context.conn)
        self.face_repo = FaceRepository(context.conn)
        self.people_list = QListWidget()
        self.people_list.setFixedWidth(200)
        self.min_conf = QDoubleSpinBox()
        self.min_conf.setRange(0.0, 1.0)
        self.min_conf.setSingleStep(0.01)
        self.min_conf.setValue(0.0)
        self.max_conf = QDoubleSpinBox()
        self.max_conf.setRange(0.0, 1.0)
        self.max_conf.setSingleStep(0.01)
        self.max_conf.setValue(1.0)
        self.unnamed_only = QCheckBox("Unnamed only (no assigned name)")
        self.refresh_btn = QPushButton("Refresh")

        self.faces_area = QScrollArea()
        self.faces_area.setWidgetResizable(True)
        self.faces_inner = QWidget()
        self.faces_layout = QGridLayout()
        self.faces_layout.setContentsMargins(8, 8, 8, 8)
        self.faces_layout.setSpacing(12)
        self.faces_inner.setLayout(self.faces_layout)
        self.faces_area.setWidget(self.faces_inner)
        self.status_label = QLabel("Select a name to review predictions.")
        self.current_tiles: list[FaceTile] = []

        self._build_ui()
        self.refresh_data()

    def _build_ui(self) -> None:
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Conf min:"))
        filters.addWidget(self.min_conf)
        filters.addWidget(QLabel("max:"))
        filters.addWidget(self.max_conf)
        filters.addWidget(self.unnamed_only)
        filters.addStretch(1)
        filters.addWidget(self.refresh_btn)

        main = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Names"))
        left.addWidget(self.people_list)
        main.addLayout(left)
        right = QVBoxLayout()
        right.addLayout(filters)
        right.addWidget(self.faces_area, stretch=1)
        right.addWidget(self.status_label)
        main.addLayout(right, stretch=1)
        self.setLayout(main)

        self.people_list.itemSelectionChanged.connect(self._on_person_selected)
        self.min_conf.valueChanged.connect(lambda _: self._load_faces())
        self.max_conf.valueChanged.connect(lambda _: self._load_faces())
        self.unnamed_only.stateChanged.connect(lambda _: self._load_faces())
        self.refresh_btn.clicked.connect(self.refresh_data)

    def _on_person_selected(self) -> None:
        self._load_faces()

    def refresh_data(self) -> None:
        """Reload people list and faces."""
        self._load_people()
        self._load_faces()

    def _load_people(self) -> None:
        self.people_list.clear()
        people = sorted(self.people_service.list_people(), key=lambda p: p.get("display_name") or p.get("primary_name"))
        counts = self._predicted_counts()
        for person in people:
            name = person.get("display_name") or person.get("primary_name") or "(unnamed)"
            count = counts.get(person.get("id"), 0)
            label = f"{name} ({count})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, person.get("id"))
            self.people_list.addItem(item)
        if self.people_list.count() and not self.people_list.selectedItems():
            self.people_list.setCurrentRow(0)

    def _predicted_counts(self) -> dict[int, int]:
        rows = self.context.conn.execute(
            """
            SELECT predicted_person_id, COUNT(*)
            FROM face
            WHERE predicted_person_id IS NOT NULL
              AND person_id IS NULL
            GROUP BY predicted_person_id
            """
        ).fetchall()
        return {int(r[0]): int(r[1]) for r in rows}

    def _selected_person_id(self) -> int | None:
        items = self.people_list.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _clear_faces(self) -> None:
        self.current_tiles = []
        while self.faces_layout.count():
            item = self.faces_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _load_faces(self) -> None:
        self._clear_faces()
        pid = self._selected_person_id()
        rows = self._fetch_faces(predicted_person_id=pid)
        if not rows:
            self.status_label.setText("No predictions to review.")
            return
        people = {p["id"]: p for p in self.people_service.list_people()}
        max_cols = 4
        for idx, row in enumerate(rows):
            tile = FaceTile(
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
                list_persons=self.people_service.list_people,
                create_person=lambda first, last, short: self.people_service.create_person(first, last, short),
                rename_person=self.people_service.rename_person,
                open_original=self._open_original_image,
            )
            tile.personAssigned.connect(lambda fid, pid, self=self: self._after_change())
            tile.personCreated.connect(lambda pid, name, self=self: self._after_change())
            tile.deleteCompleted.connect(lambda fid, self=self: self._after_change())
            row_idx, col_idx = divmod(idx, max_cols)
            self.faces_layout.addWidget(tile, row_idx, col_idx, alignment=Qt.AlignmentFlag.AlignTop)
            self.current_tiles.append(tile)
        self.status_label.setText(f"{len(rows)} faces")

    def _fetch_faces(self, predicted_person_id: int | None) -> List[FaceRow]:
        params = []
        filters = ["f.predicted_person_id IS NOT NULL"]
        if predicted_person_id is not None:
            filters.append("f.predicted_person_id = ?")
            params.append(predicted_person_id)
        if self.unnamed_only.isChecked():
            filters.append("f.person_id IS NULL")
        min_c = float(self.min_conf.value())
        max_c = float(self.max_conf.value())
        filters.append("COALESCE(f.prediction_confidence, 0) BETWEEN ? AND ?")
        params.extend([min_c, max_c])
        where = " AND ".join(filters)
        rows = self.context.conn.execute(
            f"""
            SELECT f.id, f.person_id, p.primary_name, f.predicted_person_id, pp.primary_name,
                   f.prediction_confidence, f.face_crop_blob
            FROM face f
            LEFT JOIN person p ON p.id = f.person_id
            LEFT JOIN person pp ON pp.id = f.predicted_person_id
            WHERE {where}
            ORDER BY f.id
            """,
            params,
        ).fetchall()
        results: list[FaceRow] = []
        for r in rows:
            results.append(
                FaceRow(
                    face_id=int(r[0]),
                    person_id=r[1],
                    person_name=r[2],
                    predicted_person_id=r[3],
                    predicted_name=r[4],
                    confidence=r[5],
                    crop=bytes(r[6]),
                )
            )
        return results

    def _delete_face(self, face_id: int) -> None:
        self.face_repo.delete(face_id)
        self.context.conn.commit()
        self._load_faces()
        self._load_people()

    def _assign_person(self, face_id: int, person_id: int | None) -> None:
        self.face_repo.update_person(face_id, person_id)
        self.context.conn.commit()
        self._load_faces()
        self._load_people()
    def _after_change(self) -> None:
        self._load_faces()
        self._load_people()

    def _open_original_image(self, face_id: int) -> None:
        row = self.face_repo.get_face_with_image(face_id)
        if row is None:
            return
        _, image_id, x, y, w, h, rel_path, img_w, img_h = row
        img_path = self.context.db_path.parent / rel_path
        if not img_path.exists():
            QMessageBox.warning(self, "Image missing", f"File not found: {img_path}")
            return
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
