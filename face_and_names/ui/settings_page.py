"""
Settings page with utilities, including DB reset that preserves people/groups.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from face_and_names.app_context import AppContext
from face_and_names.services.data_reset import reset_image_data


class SettingsPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.reset_btn = QPushButton("Reset database (images/faces only)")
        self.status = QLabel("")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>Settings</b>"), alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(
            QLabel("Reset will delete images, faces, metadata, sessions, stats, audit logs.")
        )
        layout.addWidget(QLabel("People, aliases, and groups are preserved."))
        layout.addWidget(self.reset_btn)
        layout.addWidget(self.status)
        layout.addStretch(1)
        self.setLayout(layout)
        self.reset_btn.clicked.connect(self._on_reset)

    def _on_reset(self) -> None:
        ret = QMessageBox.question(
            self,
            "Confirm reset",
            "Delete all imported images, faces, thumbnails, prediction data, and history?\n"
            "People/groups will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            reset_image_data(self.context.conn)
            self.status.setText("Database reset complete.")
        except Exception as exc:  # pragma: no cover - UI safety
            QMessageBox.critical(self, "Reset failed", str(exc))
            self.status.setText("Reset failed.")
