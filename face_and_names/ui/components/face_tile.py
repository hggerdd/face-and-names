"""
Reusable face tile widget skeleton.

Displays a face crop, current/predicted names, cluster badge, and supports
selection + preview hooks. Intended for use in Faces workspace/Naming/Prediction views.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget, QHBoxLayout


@dataclass
class FaceTileData:
    face_id: int
    person_name: str | None
    predicted_name: str | None
    confidence: float | None
    cluster_id: int | None
    crop: bytes


class FaceTile(QWidget):
    clicked = pyqtSignal(object)
    doubleClicked = pyqtSignal(object)
    previewRequested = pyqtSignal(object)
    deleteRequested = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data: FaceTileData | None = None
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel("")
        self.meta_label = QLabel("")

        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        layout.addWidget(self.name_label)
        layout.addWidget(self.meta_label)
        self.setLayout(layout)

    def bind(self, data: FaceTileData) -> None:
        self.data = data
        self.name_label.setText(data.person_name or "(unnamed)")
        meta_parts = []
        if data.predicted_name:
            conf = f"{data.confidence:.2f}" if data.confidence is not None else "-"
            meta_parts.append(f"Pred: {data.predicted_name} ({conf})")
        if data.cluster_id is not None:
            meta_parts.append(f"Cluster #{data.cluster_id}")
        self.meta_label.setText(" · ".join(meta_parts))

        pixmap = QPixmap()
        if pixmap.loadFromData(data.crop):
            self.image_label.setPixmap(
                pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self.data:
            self.clicked.emit(self.data)
        return super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if self.data:
            self.doubleClicked.emit(self.data)
        return super().mouseDoubleClickEvent(event)
