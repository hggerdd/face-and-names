"""Diagnostics page for local health checks."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from face_and_names.app_context import AppContext
from face_and_names.services.diagnostics_service import DiagnosticCheck, DiagnosticsService


class DiagnosticsPage(QWidget):
    """Display lightweight DB, registry, and model health checks."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.service = DiagnosticsService(
            conn=context.conn,
            db_path=context.db_path,
            registry_path=context.registry_path,
        )
        self.status_label = QLabel("")
        self.run_button = QPushButton("Run diagnostics")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Check", "Status", "Details"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._build_ui()
        self.refresh_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>Diagnostics</b>"), alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.run_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.run_button.clicked.connect(self.refresh_data)

    def refresh_data(self) -> None:
        """Run diagnostics and update the visible table."""
        result = self.service.self_test()
        status = str(result["status"])
        self.status_label.setText(f"Overall status: {status}")
        checks = result["checks"]
        if not isinstance(checks, list):
            checks = []
        self._render_checks(checks)

    def _render_checks(self, checks: list[DiagnosticCheck]) -> None:
        self.table.setRowCount(len(checks))
        for row_index, check in enumerate(checks):
            self.table.setItem(row_index, 0, QTableWidgetItem(check.name))
            self.table.setItem(row_index, 1, QTableWidgetItem(check.status))
            self.table.setItem(row_index, 2, QTableWidgetItem(check.details))
