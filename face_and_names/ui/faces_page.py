"""
Faces view: shows folders/images from DB with paging and overlays for detected faces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
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
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.image_list = QListWidget()
        self.image_list.setUniformItemSizes(True)
        self.preview = FaceImageView()
        self.status = QLabel("Select a folder")
        self.load_more_btn = QPushButton("Load more")
        self.load_more_btn.clicked.connect(self._load_more)
        self.load_more_btn.setEnabled(False)
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
        root_layout.addWidget(self.status)
        self.setLayout(root_layout)

        self.tree.itemSelectionChanged.connect(self._on_folder_selected)
        self.image_list.itemSelectionChanged.connect(self._on_image_selected)

        self._load_folders()

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
