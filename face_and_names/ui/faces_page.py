"""Unified Faces workspace with face-first browsing and bulk actions."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from face_and_names.app_context import AppContext
from face_and_names.services.faces_workspace_controller import (
    FacesWorkspaceController,
    FaceTileRecord,
    FaceWorkspaceFilters,
    WorkspaceMode,
)
from face_and_names.ui.components.face_tile import FaceTile, FaceTileData, PersonSelectDialog


class FaceImageView(QGraphicsView):
    """Graphics view that draws pixmap and face boxes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(self.renderHints() | QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background: #222;")

    def show_image(self, pixmap: QPixmap, boxes: list[tuple[float, float, float, float]]) -> None:
        scene = self.scene()
        scene.clear()
        pix_item = QGraphicsPixmapItem(pixmap)
        scene.addItem(pix_item)
        pw = pixmap.width()
        ph = pixmap.height()
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(2)
        brush = QBrush(Qt.BrushStyle.NoBrush)
        for x_rel, y_rel, w_rel, h_rel in boxes:
            rect = QGraphicsRectItem(x_rel * pw, y_rel * ph, w_rel * pw, h_rel * ph)
            rect.setPen(pen)
            rect.setBrush(brush)
            scene.addItem(rect)
        self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class FacesPage(QWidget):
    """Face-first workspace for filtering, reviewing, and assigning faces."""

    PAGE_SIZE = 40
    GRID_COLUMNS = 5

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.people_service = context.people_service
        self.controller = FacesWorkspaceController(
            context.conn, context.db_path.parent, context.people_service
        )
        self.current_folder: str | None = None
        self.current_mode: WorkspaceMode = "all"
        self.current_page = 0
        self.total_faces = 0
        self.current_tiles: list[FaceTile] = []
        self.selected_face_ids: set[int] = set()

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("All", userData="all")
        self.mode_combo.addItem("Unnamed", userData="unnamed")
        self.mode_combo.addItem("Predicted", userData="predicted")
        self.mode_combo.addItem("Clustered", userData="clustered")
        self.min_conf = QDoubleSpinBox()
        self.min_conf.setRange(0.0, 1.0)
        self.min_conf.setSingleStep(0.01)
        self.min_conf.setValue(0.0)
        self.max_conf = QDoubleSpinBox()
        self.max_conf.setRange(0.0, 1.0)
        self.max_conf.setSingleStep(0.01)
        self.max_conf.setValue(1.0)
        self.differs_checkbox = QCheckBox("Prediction differs")
        self.refresh_btn = QPushButton("Refresh")
        self.prev_btn = QPushButton("<")
        self.next_btn = QPushButton(">")
        self.page_label = QLabel("Page 1/1")
        self.summary_label = QLabel("")
        self.status = QLabel("")

        self.faces_area = QScrollArea()
        self.faces_area.setWidgetResizable(True)
        self.faces_inner = QWidget()
        self.faces_layout = QGridLayout()
        self.faces_layout.setContentsMargins(8, 8, 8, 8)
        self.faces_layout.setSpacing(12)
        self.faces_inner.setLayout(self.faces_layout)
        self.faces_area.setWidget(self.faces_inner)

        self.context_title = QLabel("<b>Workspace</b>")
        self.context_counts = QLabel("")
        self.selection_label = QLabel("0 selected")
        self.accept_predictions_btn = QPushButton("Accept selected predictions")
        self.assign_person_btn = QPushButton("Assign selected person")
        self.clear_names_btn = QPushButton("Clear selected names")

        self._build_ui()
        self._bind_events()
        self.refresh_data()
        try:
            self.context.events.subscribe("ingest_completed", self._on_external_refresh)
            self.context.events.subscribe("clustering_completed", self._on_external_refresh)
        except Exception:
            pass

    def _build_ui(self) -> None:
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Mode:"))
        filters.addWidget(self.mode_combo)
        filters.addWidget(QLabel("Confidence:"))
        filters.addWidget(self.min_conf)
        filters.addWidget(QLabel("to"))
        filters.addWidget(self.max_conf)
        filters.addWidget(self.differs_checkbox)
        filters.addWidget(self.refresh_btn)
        filters.addStretch(1)

        left = QWidget()
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Scope"))
        left_layout.addWidget(self.tree)
        left.setLayout(left_layout)

        center = QWidget()
        center_layout = QVBoxLayout()
        pager = QHBoxLayout()
        pager.addWidget(self.prev_btn)
        pager.addWidget(self.page_label)
        pager.addWidget(self.next_btn)
        pager.addStretch(1)
        pager.addWidget(self.summary_label)
        center_layout.addLayout(pager)
        center_layout.addWidget(self.faces_area, stretch=1)
        center_layout.addWidget(self.status)
        center.setLayout(center_layout)

        right = QWidget()
        right.setFixedWidth(260)
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.context_title)
        right_layout.addWidget(self.context_counts)
        right_layout.addWidget(self.selection_label)
        right_layout.addWidget(self.accept_predictions_btn)
        right_layout.addWidget(self.assign_person_btn)
        right_layout.addWidget(self.clear_names_btn)
        right_layout.addStretch(1)
        right.setLayout(right_layout)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        root = QVBoxLayout()
        root.addLayout(filters)
        root.addWidget(splitter, stretch=1)
        self.setLayout(root)

    def _bind_events(self) -> None:
        self.tree.itemSelectionChanged.connect(self._on_scope_changed)
        self.mode_combo.currentIndexChanged.connect(self._reset_and_load)
        self.min_conf.valueChanged.connect(self._reset_and_load)
        self.max_conf.valueChanged.connect(self._reset_and_load)
        self.differs_checkbox.stateChanged.connect(self._reset_and_load)
        self.refresh_btn.clicked.connect(self.refresh_data)
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)
        self.accept_predictions_btn.clicked.connect(self._accept_selected_predictions)
        self.assign_person_btn.clicked.connect(self._assign_selected_person)
        self.clear_names_btn.clicked.connect(self._clear_selected_names)

    def refresh_data(self) -> None:
        """Reload scopes, counts, and the current face page."""
        self._load_folders()
        self._refresh_summary()
        self._load_face_page()

    def _on_external_refresh(self, *args, **kwargs) -> None:
        self.refresh_data()
        self.status.setText("Refreshed after external update")

    def _load_folders(self) -> None:
        current = self.current_folder
        self.tree.clear()
        root = QTreeWidgetItem(["All folders"])
        root.setData(0, Qt.ItemDataRole.UserRole, None)
        self.tree.addTopLevelItem(root)
        selected_item = root if current is None else None
        for sub in self.controller.list_folders():
            if not sub:
                continue
            parts = sub.split("/")
            parent = root
            path_acc: list[str] = []
            for part in parts:
                path_acc.append(part)
                path = "/".join(path_acc)
                existing = None
                for index in range(parent.childCount()):
                    if parent.child(index).text(0) == part:
                        existing = parent.child(index)
                        break
                if existing is None:
                    existing = QTreeWidgetItem([part])
                    existing.setData(0, Qt.ItemDataRole.UserRole, path)
                    parent.addChild(existing)
                if path == current:
                    selected_item = existing
                parent = existing
        self.tree.expandAll()
        self.tree.setCurrentItem(selected_item or root)

    def _on_scope_changed(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        self.current_folder = items[0].data(0, Qt.ItemDataRole.UserRole)
        self._reset_and_load()

    def _reset_and_load(self) -> None:
        mode = self.mode_combo.currentData()
        self.current_mode = mode if mode in {"all", "unnamed", "predicted", "clustered"} else "all"
        self.current_page = 0
        self._refresh_summary()
        self._load_face_page()

    def _filters(self) -> FaceWorkspaceFilters:
        return FaceWorkspaceFilters(
            folder=self.current_folder,
            mode=self.current_mode,
            confidence_min=float(self.min_conf.value()),
            confidence_max=float(self.max_conf.value()),
            differs_from_name=self.differs_checkbox.isChecked(),
        )

    def _load_face_page(self) -> None:
        self._clear_faces()
        result = self.controller.load_face_page(
            self._filters(),
            offset=self.current_page * self.PAGE_SIZE,
            limit=self.PAGE_SIZE,
        )
        self.total_faces = result.total
        total_pages = max(1, (self.total_faces + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)
            result = self.controller.load_face_page(
                self._filters(),
                offset=self.current_page * self.PAGE_SIZE,
                limit=self.PAGE_SIZE,
            )
        self.page_label.setText(f"Page {self.current_page + 1}/{total_pages}")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)
        for index, row in enumerate(result.faces):
            tile = self._build_face_tile(row)
            self.faces_layout.addWidget(
                tile,
                index // self.GRID_COLUMNS,
                index % self.GRID_COLUMNS,
            )
            self.current_tiles.append(tile)
            self.selected_face_ids.add(row.face_id)
        self._update_context_panel()
        if not result.faces:
            self.status.setText("No faces match the current filters.")
        else:
            self.status.setText(f"Showing {len(result.faces)} of {self.total_faces} faces.")

    def _build_face_tile(self, row: FaceTileRecord) -> FaceTile:
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
            create_person=self._create_person,
            rename_person=self.people_service.rename_person,
            open_original=self._open_original_image,
            confirm_delete=self._confirm_delete_enabled(),
        )
        tile.selectionChanged.connect(self._on_tile_selection_changed)
        tile.deleteCompleted.connect(lambda _face_id: self._reload_after_change())
        tile.personAssigned.connect(lambda _face_id, _person_id: self._reload_after_change())
        tile.personCreated.connect(lambda _person_id, _name: self._reload_after_change())
        tile.personRenamed.connect(lambda _person_id, _name: self._reload_after_change())
        return tile

    def _clear_faces(self) -> None:
        self.current_tiles = []
        self.selected_face_ids.clear()
        while self.faces_layout.count():
            item = self.faces_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _on_tile_selection_changed(self, face_id: int, selected: bool) -> None:
        if selected:
            self.selected_face_ids.add(face_id)
        else:
            self.selected_face_ids.discard(face_id)
        self._update_context_panel()

    def _update_context_panel(self) -> None:
        summary = self.controller.workspace_summary(folder=self.current_folder)
        self.context_counts.setText(
            f"{summary.faces} faces\n"
            f"{summary.unnamed_faces} unnamed\n"
            f"{summary.predicted_faces} predicted\n"
            f"{summary.clustered_faces} clustered"
        )
        self.summary_label.setText(
            f"{summary.images} images | {summary.faces} faces | {summary.unnamed_faces} unnamed"
        )
        self.selection_label.setText(f"{len(self.selected_face_ids)} selected")

    def _refresh_summary(self) -> None:
        self._update_context_panel()

    def _prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self._load_face_page()

    def _next_page(self) -> None:
        self.current_page += 1
        self._load_face_page()

    def _selected_ids(self) -> list[int]:
        return sorted(self.selected_face_ids)

    def _accept_selected_predictions(self) -> None:
        changed = self.controller.accept_predictions(self._selected_ids())
        self.status.setText(f"Accepted predictions for {changed} faces.")
        self._reload_after_change()

    def _assign_selected_person(self) -> None:
        persons = list(self.people_service.list_people())
        dialog = PersonSelectDialog(
            persons=persons,
            create_person=self._create_person,
            rename_person=self.people_service.rename_person,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_person_id is None:
            return
        changed = self.controller.assign_person_to_faces(
            self._selected_ids(), dialog.selected_person_id
        )
        self.status.setText(f"Assigned person to {changed} faces.")
        self._reload_after_change()

    def _clear_selected_names(self) -> None:
        changed = self.controller.assign_person_to_faces(self._selected_ids(), None)
        self.status.setText(f"Cleared names for {changed} faces.")
        self._reload_after_change()

    def _reload_after_change(self) -> None:
        self._refresh_summary()
        self._load_face_page()

    def _delete_face(self, face_id: int) -> None:
        self.controller.delete_face(face_id)

    def _assign_person(self, face_id: int, person_id: int | None) -> None:
        self.controller.assign_person(face_id, person_id)

    def _create_person(self, first: str, last: str, short_name: str | None = None) -> int:
        return self.controller.create_person(first, last, short_name=short_name)

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
        if isinstance(self.context.config, dict):
            return bool(self.context.config.get("ui", {}).get("confirm_delete_face", True))
        return True
