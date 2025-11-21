"""
Main window shell for Face-and-Names v2.

Creates the navigation frame and placeholder views aligned to docs/ui_wireframes.md.
"""

from __future__ import annotations

from typing import Dict, List

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
from face_and_names.ui.import_page import ImportPage
from face_and_names.ui.faces_page import FacesPage
from face_and_names.ui.clustering_page import ClusteringPage


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

        self._add_page(
            "Faces",
            placeholder="Faces workspace: clusters/predictions/people views",
            widget=FacesPage(self.context),
        )
        self._add_page(
            "Import",
            placeholder="Ingest photos from DB Root with progress/resume",
            widget=ImportPage(self.context, on_context_changed=self._replace_context),
        )
        self._add_page(
            "Clustering",
            placeholder="Configure and run clustering jobs",
            widget=ClusteringPage(self.context),
        )
        self._add_page("Prediction Review", "Review and accept model predictions")
        self._add_page("People & Groups", "Manage people records, aliases, groups")
        self._add_page("Diagnostics", "Model/DB health, self-test, repair tools")
        self._add_page("Settings", "App preferences, device/worker caps, paths")

        # Default selection
        if self.nav.count():
            self.nav.setCurrentRow(0)

    def _add_page(self, name: str, placeholder: str, widget: QWidget | None = None) -> None:
        """Add a nav item and corresponding page."""
        item = QListWidgetItem(name)
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.nav.addItem(item)

        if widget is None:
            page = QWidget(self)
            vbox = QVBoxLayout()
            vbox.addWidget(QLabel(f"<b>{name}</b>"), alignment=Qt.AlignmentFlag.AlignTop)
            vbox.addWidget(QLabel(placeholder))
            vbox.addStretch(1)
            page.setLayout(vbox)
        else:
            page = widget

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

    def _replace_context(self, new_context: AppContext) -> None:
        """Replace shared context when DB Root changes."""
        self.context = new_context
