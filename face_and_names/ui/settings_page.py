"""
Settings page with utilities, including DB reset that preserves people/groups.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from face_and_names.app_context import AppContext
from face_and_names.services.settings_controller import SettingsController


class SettingsPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.controller = SettingsController(context.conn)
        self.reset_btn = QPushButton("Reset database (images/faces only)")
        self.status = QLabel("")
        self.confirm_delete_checkbox = QCheckBox("Confirm face delete actions")
        current = (
            bool(self.context.config.get("ui", {}).get("confirm_delete_face"))
            if isinstance(self.context.config, dict)
            else True
        )
        self.confirm_delete_checkbox.setChecked(current)
        self.confirm_delete_checkbox.stateChanged.connect(self._on_confirm_delete_changed)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(QLabel("<h2>Settings</h2>"), alignment=Qt.AlignmentFlag.AlignTop)
        intro = QLabel("Configure local behavior and maintenance actions for the active DB Root.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(QLabel("<b>Safety</b>"))
        layout.addWidget(self.confirm_delete_checkbox)
        layout.addWidget(QLabel("<b>Database maintenance</b>"))
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
            self.controller.reset_imported_data()
            self.status.setText("Database reset complete.")
        except Exception as exc:  # pragma: no cover - UI safety
            QMessageBox.critical(self, "Reset failed", str(exc))
            self.status.setText("Reset failed.")

    def confirm_delete_enabled(self) -> bool:
        """Return current checkbox value for delete confirmations."""
        return self.confirm_delete_checkbox.isChecked()

    def _on_confirm_delete_changed(self, state: int) -> None:
        try:
            if not isinstance(self.context.config, dict):
                return
            ui_cfg = self.context.config.setdefault("ui", {})
            ui_cfg["confirm_delete_face"] = bool(state)
        except Exception:
            pass
