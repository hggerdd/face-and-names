"""
Prediction Review page: fast verification of predicted names.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
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
)

from face_and_names.app_context import AppContext
from face_and_names.services.prediction_review_controller import (
    PredictionReviewController,
    PredictionReviewFilters,
)
from face_and_names.ui.components.face_tile import FaceTile, FaceTileData
from face_and_names.ui.faces_page import FaceImageView


class PredictionReviewPage(QWidget):
    PAGE_SIZE = 20

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.people_service = context.people_service
        self.controller = PredictionReviewController(context.conn, context.db_path.parent)
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
        self.unnamed_only = QCheckBox("Only faces without assigned person")
        self.refresh_btn = QPushButton("Refresh")
        self.accept_btn = QPushButton("Accept selected predictions")

        # Pagination controls
        self.prev_btn = QPushButton("<")
        self.next_btn = QPushButton(">")
        self.page_label = QLabel("Page 1/1")
        self.current_page = 0

        self.faces_area = QScrollArea()
        self.faces_area.setWidgetResizable(True)
        self.faces_inner = QWidget()
        self.faces_layout = QGridLayout()
        self.faces_layout.setContentsMargins(8, 8, 8, 8)
        self.faces_layout.setSpacing(12)
        self.faces_inner.setLayout(self.faces_layout)
        self.faces_area.setWidget(self.faces_inner)
        self.status_label = QLabel(
            "Advanced prediction review. The main review workflow is in Faces."
        )
        self.current_tiles: list[FaceTile] = []

        self._build_ui()
        self.refresh_data()

    def _build_ui(self) -> None:
        title = QVBoxLayout()
        heading = QLabel("<h2>Advanced Prediction Review</h2>")
        intro = QLabel(
            "Use this legacy view for person-specific prediction review. Prefer Faces for the unified workflow."
        )
        intro.setWordWrap(True)
        title.addWidget(heading)
        title.addWidget(intro)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Confidence:"))
        filters.addWidget(self.min_conf)
        filters.addWidget(QLabel("to"))
        filters.addWidget(self.max_conf)
        filters.addWidget(self.unnamed_only)
        filters.addStretch(1)
        filters.addWidget(self.refresh_btn)
        filters.addWidget(self.accept_btn)

        # Pagination UI centered above images
        pagination_layout = QHBoxLayout()
        pagination_layout.addStretch(1)
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch(1)

        main = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Predicted person"))
        left.addWidget(self.people_list)
        main.addLayout(left)

        right = QVBoxLayout()
        right.addLayout(title)
        right.addLayout(filters)
        right.addLayout(pagination_layout)
        right.addWidget(self.faces_area, stretch=1)
        right.addWidget(self.status_label)
        main.addLayout(right, stretch=1)
        self.setLayout(main)

        self.people_list.itemSelectionChanged.connect(self._on_person_selected)
        self.min_conf.valueChanged.connect(self._reset_and_load)
        self.max_conf.valueChanged.connect(self._reset_and_load)
        self.unnamed_only.stateChanged.connect(self._reset_and_load)
        self.refresh_btn.clicked.connect(self.refresh_data)
        self.accept_btn.clicked.connect(self._accept_predictions)

        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)

    def _on_person_selected(self) -> None:
        self.current_page = 0
        self._load_faces()

    def _reset_and_load(self) -> None:
        self.current_page = 0
        self._load_faces()

    def _prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self._load_faces()

    def _next_page(self) -> None:
        self.current_page += 1
        self._load_faces()

    def refresh_data(self) -> None:
        """Reload people list and faces."""
        self._load_people()
        self._load_faces()

    def _load_people(self) -> None:
        current_id = self._selected_person_id()
        self.people_list.clear()
        people = sorted(
            self.people_service.list_people(),
            key=lambda p: p.get("display_name") or p.get("primary_name"),
        )
        counts = self.controller.predicted_counts()
        for person in people:
            name = person.get("display_name") or person.get("primary_name") or "(unnamed)"
            count = counts.get(person.get("id"), 0)
            label = f"{name} ({count})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, person.get("id"))
            self.people_list.addItem(item)
        # Preserve previous selection when possible
        if current_id is not None:
            for row in range(self.people_list.count()):
                if self.people_list.item(row).data(Qt.ItemDataRole.UserRole) == current_id:
                    self.people_list.setCurrentRow(row)
                    break
        elif self.people_list.count() and not self.people_list.selectedItems():
            self.people_list.setCurrentRow(0)

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

    def _filters(self) -> PredictionReviewFilters:
        return PredictionReviewFilters(
            predicted_person_id=self._selected_person_id(),
            confidence_min=float(self.min_conf.value()),
            confidence_max=float(self.max_conf.value()),
            unnamed_only=self.unnamed_only.isChecked(),
        )

    def _load_faces(self) -> None:
        self._clear_faces()
        filters = self._filters()
        total_count = self.controller.count_faces(filters)
        total_pages = max(1, (total_count + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

        # Clamp current page
        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)

        offset = self.current_page * self.PAGE_SIZE
        rows = self.controller.load_faces(filters, limit=self.PAGE_SIZE, offset=offset)

        # Update pagination UI
        self.page_label.setText(f"{self.current_page + 1}/{total_pages}")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

        if not rows:
            self.status_label.setText("No predictions to review.")
            return

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
                create_person=lambda first, last, short: self.people_service.create_person(
                    first, last, short
                ),
                rename_person=self.people_service.rename_person,
                open_original=self._open_original_image,
                confirm_delete=self._confirm_delete_enabled(),
            )
            tile.personAssigned.connect(lambda fid, pid, self=self: self._after_change())
            tile.personCreated.connect(lambda pid, name, self=self: self._after_change())
            tile.deleteCompleted.connect(lambda fid, self=self: self._after_change())
            row_idx, col_idx = divmod(idx, max_cols)
            self.faces_layout.addWidget(tile, row_idx, col_idx, alignment=Qt.AlignmentFlag.AlignTop)
            self.current_tiles.append(tile)
        self.status_label.setText(f"Showing {len(rows)} faces (Total: {total_count})")

    def _delete_face(self, face_id: int) -> None:
        self.controller.delete_face(face_id)
        self._load_faces()
        self._load_people()

    def _assign_person(self, face_id: int, person_id: int | None) -> None:
        self.controller.assign_person(face_id, person_id)
        self._load_faces()
        self._load_people()

    def _selected_tiles(self) -> list[FaceTile]:
        return [t for t in self.current_tiles if t.is_selected()]

    def _accept_predictions(self) -> None:
        tiles = self._selected_tiles()
        if not tiles:
            QMessageBox.information(
                self, "No selection", "Select one or more faces to accept predictions."
            )
            return
        try:
            self.controller.accept_predictions([tile.data.face_id for tile in tiles])
            self._load_faces()
            self._load_people()
        except Exception as exc:  # pragma: no cover - UI safety
            QMessageBox.critical(self, "Accept failed", str(exc))

    def _after_change(self) -> None:
        # Don't reset page on single action, just reload current page
        self._load_faces()
        self._load_people()

    def _open_original_image(self, face_id: int) -> None:
        original = self.controller.get_original_face_image(face_id)
        if original is None:
            return
        if not original.image_path.exists():
            QMessageBox.warning(self, "Image missing", f"File not found: {original.image_path}")
            return
        pix = QPixmap(str(original.image_path))
        window = QDialog(self)
        window.setWindowTitle("Original image")
        view = FaceImageView()
        view.show_image(pix, [original.bbox_rel])
        layout = QVBoxLayout()
        layout.addWidget(view)
        window.setLayout(layout)
        window.resize(800, 600)
        window.exec()

    def _confirm_delete_enabled(self) -> bool:
        cfg = getattr(self.context, "config", None)
        if isinstance(cfg, dict):
            return bool(cfg.get("ui", {}).get("confirm_delete_face", True))
        return True
