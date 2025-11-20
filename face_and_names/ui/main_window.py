"""
Main window shell for Face-and-Names v2.

Creates the navigation frame and placeholder views aligned to docs/ui_wireframes.md.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
)

from face_and_names.app_context import AppContext


class MainWindow(QMainWindow):
    """Initial UI shell with nav + stacked placeholders."""

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("Face-and-Names v2")

        self.nav = QListWidget(self)
        self.stacked = QStackedWidget(self)
        self._pages: Dict[str, QWidget] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        """Construct layout for navigation and placeholder pages."""
        container = QWidget(self)
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        self.nav.setFixedWidth(180)
        self.nav.setSpacing(4)
        self.nav.itemSelectionChanged.connect(self._on_nav_changed)

        layout.addWidget(self.nav)
        layout.addWidget(self.stacked, stretch=1)

        container.setLayout(layout)
        self.setCentralWidget(container)

        self._add_page("Faces", "Faces workspace: clusters/predictions/people views")
        self._add_page("Import", "Ingest photos from DB Root with progress/resume")
        self._add_page("Clustering", "Configure and run clustering jobs")
        self._add_page("Prediction Review", "Review and accept model predictions")
        self._add_page("People & Groups", "Manage people records, aliases, groups")
        self._add_page("Diagnostics", "Model/DB health, self-test, repair tools")
        self._add_page("Settings", "App preferences, device/worker caps, paths")

        # Default selection
        if self.nav.count():
            self.nav.setCurrentRow(0)

    def _add_page(self, name: str, description: str) -> None:
        """Add a nav item and corresponding placeholder page."""
        item = QListWidgetItem(name)
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.nav.addItem(item)

        page = QWidget(self)
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel(f"<b>{name}</b>"), alignment=Qt.AlignmentFlag.AlignTop)
        vbox.addWidget(QLabel(description))
        vbox.addStretch(1)
        page.setLayout(vbox)

        self.stacked.addWidget(page)
        self._pages[name] = page

    def _on_nav_changed(self) -> None:
        """Switch stacked widget when nav selection changes."""
        current_items: List[QListWidgetItem] = self.nav.selectedItems()
        if not current_items:
            return
        name = current_items[0].text()
        index = self.nav.row(current_items[0])
        if name in self._pages:
            self.stacked.setCurrentIndex(index)
