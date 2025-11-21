"""
Faces view: shows folders/images from DB with paging and overlays for detected faces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from face_and_names.models.repositories import FaceRepository
from face_and_names.services.people_service import PeopleService
from face_and_names.ui.components.face_tile import FaceTile, FaceTileData
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPen, QPixmap, QPainter
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QDialog,
    QMessageBox,
)

from face_and_names.app_context import AppContext


@dataclass
class ImageRecord:
    image_id: int
    filename: str
    relative_path: str
    thumb: bytes
    width: int
    height: int


class FaceImageView(QGraphicsView):
    """Graphics view that draws pixmap and face boxes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(self.renderHints() | QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background: #222;")

    def show_image(self, pixmap: QPixmap, boxes: List[tuple[float, float, float, float]]) -> None:
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
    """
    Faces tab with folder tree, image list (paged), and preview with face overlays.
    Paging keeps the UI responsive for large folders until full virtualization is wired.
    """

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.people_service = PeopleService(context.conn)
        self.face_repo = FaceRepository(context.conn)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.image_list = QListWidget()
        self.image_list.setUniformItemSizes(True)
        self.preview = FaceImageView()
        self.status = QLabel("Select a folder")
        self.load_more_btn = QPushButton("Load more")
        self.load_more_btn.clicked.connect(self._load_more)
        self.load_more_btn.setEnabled(False)
        self.face_table = QTableWidget(0, 3)
        self.face_table.setHorizontalHeaderLabels(["Person", "Predicted", "Confidence"])
        self.face_table.horizontalHeader().setStretchLastSection(True)
        self.face_table.verticalHeader().setVisible(False)
        self.face_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.face_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.face_tiles_area = QScrollArea()
        self.face_tiles_area.setWidgetResizable(True)
        self.face_tiles_inner = QWidget()
        self.face_tiles_layout = QHBoxLayout()
        self.face_tiles_layout.setContentsMargins(4, 4, 4, 4)
        self.face_tiles_layout.setSpacing(8)
        self.face_tiles_inner.setLayout(self.face_tiles_layout)
        self.face_tiles_area.setWidget(self.face_tiles_inner)
        self.page_size = 200
        self.current_folder: str = ""
        self.current_offset = 0
        self.total_images = 0

        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Folders"))
        left_layout.addWidget(self.tree)
        left_layout.addWidget(QLabel("Images"))
        left_layout.addWidget(self.image_list)
        left_layout.addWidget(self.load_more_btn)
        left.setLayout(left_layout)
        splitter.addWidget(left)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(1, 1)

        root_layout = QVBoxLayout()
        root_layout.addWidget(splitter)
        root_layout.addWidget(QLabel("Faces in image:"))
        root_layout.addWidget(self.face_table)
        root_layout.addWidget(QLabel("Face tiles:"))
        root_layout.addWidget(self.face_tiles_area)
        root_layout.addWidget(self.status)
        self.setLayout(root_layout)

        self.tree.itemSelectionChanged.connect(self._on_folder_selected)
        self.image_list.itemSelectionChanged.connect(self._on_image_selected)

        self._load_folders()
        # Refresh when ingest or clustering completes
        try:
            self.context.events.subscribe("ingest_completed", self._on_external_refresh)
            self.context.events.subscribe("clustering_completed", self._on_external_refresh)
        except Exception:
            pass

    def _on_external_refresh(self, *args, **kwargs) -> None:
        """Refresh folders/images when data changes elsewhere."""
        self._load_folders()
        self.image_list.clear()
        self.face_table.setRowCount(0)
        self.preview.scene().clear()
        self.status.setText("Refreshed after external update")

    def _load_folders(self) -> None:
        self.tree.clear()
        rows = self.context.conn.execute(
            "SELECT DISTINCT sub_folder FROM image ORDER BY sub_folder"
        ).fetchall()
        root = QTreeWidgetItem(["/"])
        self.tree.addTopLevelItem(root)
        for (sub,) in rows:
            if not sub:
                continue
            parts = sub.split("/")
            parent = root
            path_acc = []
            for part in parts:
                path_acc.append(part)
                existing = None
                for i in range(parent.childCount()):
                    if parent.child(i).text(0) == part:
                        existing = parent.child(i)
                        break
                if existing is None:
                    existing = QTreeWidgetItem([part])
                    existing.setData(0, Qt.ItemDataRole.UserRole, "/".join(path_acc))
                    parent.addChild(existing)
                parent = existing
        self.tree.expandAll()

    def _on_folder_selected(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        folder = items[0].data(0, Qt.ItemDataRole.UserRole)
        self.current_folder = folder or ""
        self.current_offset = 0
        self.image_list.clear()
        self._load_page(reset=True)

    def _load_page(self, reset: bool = False) -> None:
        imgs, total = self._load_images(self.current_folder, offset=self.current_offset, limit=self.page_size)
        if reset:
            self.image_list.clear()
        for rec in imgs:
            item = QListWidgetItem(rec.filename)
            item.setData(Qt.ItemDataRole.UserRole, rec)
            self.image_list.addItem(item)
        self.current_offset += len(imgs)
        self.total_images = total
        self.load_more_btn.setEnabled(self.current_offset < self.total_images)
        self.status.setText(f"{self.current_offset}/{self.total_images} images in /{self.current_folder or '/'}")

    def _load_more(self) -> None:
        self._load_page(reset=False)

    def _load_images(self, folder: str, offset: int, limit: int) -> tuple[List[ImageRecord], int]:
        total = self.context.conn.execute(
            "SELECT COUNT(*) FROM image WHERE sub_folder = ?", (folder,),
        ).fetchone()[0]
        rows = self.context.conn.execute(
            """
            SELECT id, filename, relative_path, thumbnail_blob, width, height
            FROM image
            WHERE sub_folder = ?
            ORDER BY filename
            LIMIT ? OFFSET ?
            """,
            (folder, limit, offset),
        ).fetchall()
        return [
            ImageRecord(
                image_id=row[0],
                filename=row[1],
                relative_path=row[2],
                thumb=row[3],
                width=row[4],
                height=row[5],
            )
            for row in rows
        ], total

    def _on_image_selected(self) -> None:
        items = self.image_list.selectedItems()
        if not items:
            return
        rec: ImageRecord = items[0].data(Qt.ItemDataRole.UserRole)
        pix = QPixmap()
        if not pix.loadFromData(rec.thumb):
            self.status.setText("Failed to load thumbnail")
            return
        boxes = self._load_face_boxes(rec.image_id)
        self.preview.show_image(pix, boxes)
        self._load_face_table(rec.image_id)
        self._load_face_tiles(rec.image_id)
        self.status.setText(f"{rec.filename}: {len(boxes)} faces")

    def _load_face_boxes(self, image_id: int) -> List[tuple[float, float, float, float]]:
        rows = self.context.conn.execute(
            """
            SELECT bbox_rel_x, bbox_rel_y, bbox_rel_w, bbox_rel_h
            FROM face
            WHERE image_id = ?
            """,
            (image_id,),
        ).fetchall()
        return [(float(r[0]), float(r[1]), float(r[2]), float(r[3])) for r in rows]

    def _load_face_tiles(self, image_id: int) -> None:
        # Clear existing
        while self.face_tiles_layout.count():
            item = self.face_tiles_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        rows = self.context.conn.execute(
            """
            SELECT f.id, f.person_id, p.primary_name, f.predicted_person_id, pp.primary_name, f.prediction_confidence, f.face_crop_blob
            FROM face f
            LEFT JOIN person p ON p.id = f.person_id
            LEFT JOIN person pp ON pp.id = f.predicted_person_id
            WHERE f.image_id = ?
            ORDER BY f.id
            """,
            (image_id,),
        ).fetchall()
        for row in rows:
            data = FaceTileData(
                face_id=int(row[0]),
                person_id=row[1],
                person_name=row[2],
                predicted_person_id=row[3],
                predicted_name=row[4],
                confidence=row[5],
                crop=bytes(row[6]),
            )
            tile = FaceTile(
                data,
                delete_face=self._delete_face,
                assign_person=self._assign_person,
                list_persons=self.people_service.list_people,
                create_person=self._create_person,
                rename_person=self.people_service.rename_person,
                open_original=self._open_original_image,
            )
            tile.deleteCompleted.connect(self._on_face_deleted)
            tile.personAssigned.connect(lambda fid, pid, img_id=image_id: self._refresh_after_change(img_id))
            tile.personCreated.connect(lambda _, __, img_id=image_id: self._refresh_after_change(img_id))
            tile.personRenamed.connect(lambda _, __, img_id=image_id: self._refresh_after_change(img_id))
            self.face_tiles_layout.addWidget(tile)
        self.face_tiles_layout.addStretch(1)

    def _refresh_after_change(self, image_id: int) -> None:
        self._load_face_tiles(image_id)
        boxes = self._load_face_boxes(image_id)
        if self.image_list.selectedItems():
            rec: ImageRecord = self.image_list.selectedItems()[0].data(Qt.ItemDataRole.UserRole)
            pix = QPixmap()
            if pix.loadFromData(rec.thumb):
                self.preview.show_image(pix, boxes)
        self._load_face_table(image_id)

    def _delete_face(self, face_id: int) -> None:
        self.face_repo.delete(face_id)
        self.context.conn.commit()

    def _assign_person(self, face_id: int, person_id: int | None) -> None:
        self.face_repo.update_person(face_id, person_id)
        self.context.conn.commit()

    def _create_person(self, name: str) -> int:
        return self.people_service.create_person(name)

    def _on_face_deleted(self, face_id: int) -> None:
        # Refresh current image view if visible
        items = self.image_list.selectedItems()
        if items:
            rec: ImageRecord = items[0].data(Qt.ItemDataRole.UserRole)
            self._refresh_after_change(rec.image_id)

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

    def _load_face_table(self, image_id: int) -> None:
        rows = self.context.conn.execute(
            """
            SELECT
                COALESCE(p.primary_name, '') AS person_name,
                COALESCE(pp.primary_name, '') AS predicted_name,
                COALESCE(f.prediction_confidence, 0)
            FROM face f
            LEFT JOIN person p ON p.id = f.person_id
            LEFT JOIN person pp ON pp.id = f.predicted_person_id
            WHERE f.image_id = ?
            ORDER BY f.id
            """,
            (image_id,),
        ).fetchall()
        self.face_table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            self.face_table.setItem(idx, 0, QTableWidgetItem(row[0]))
            self.face_table.setItem(idx, 1, QTableWidgetItem(row[1]))
            conf = "" if row[2] is None else f"{float(row[2]):.2f}"
            self.face_table.setItem(idx, 2, QTableWidgetItem(conf))
