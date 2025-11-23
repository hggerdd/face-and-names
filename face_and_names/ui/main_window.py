"""
Main window shell for Face-and-Names v2.

Creates the navigation frame and placeholder views aligned to docs/ui_wireframes.md.
"""

from __future__ import annotations

from typing import Callable, Dict

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
from face_and_names.models.db import initialize_database
from face_and_names.services.people_service import PeopleService


class MainWindow(QMainWindow):
    """Initial UI shell with nav + stacked placeholders."""

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("Face-and-Names v2")

        self.nav = QListWidget(self)
        self.stacked = QStackedWidget(self)
        self._pages: Dict[str, QWidget] = {}
        self._factories: Dict[str, Callable[[], QWidget]] = {}

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

        # Factories for lazy loading
        # FacesPage is default, so we can load it eagerly or lazy-but-immediately-triggered
        def create_faces():
            from face_and_names.ui.faces_page import FacesPage
            return FacesPage(self.context)

        def create_import():
            from face_and_names.ui.import_page import ImportPage
            return ImportPage(self.context, on_context_changed=self._replace_context)

        def create_clustering():
            from face_and_names.ui.clustering_page import ClusteringPage
            return ClusteringPage(self.context)

        def create_training():
            from face_and_names.ui.prediction_training_page import PredictionTrainingPage
            return PredictionTrainingPage(self.context)

        def create_review():
            from face_and_names.ui.prediction_review_page import PredictionReviewPage
            return PredictionReviewPage(self.context)

        def create_people():
            from face_and_names.ui.people_groups_page import PeopleGroupsPage
            return PeopleGroupsPage(self._ensure_people_service)

        def create_settings():
            from face_and_names.ui.settings_page import SettingsPage
            return SettingsPage(self.context)

        self._add_page("Faces", "Faces workspace: clusters/predictions/people views", factory=create_faces)
        self._add_page("Import", "Ingest photos from DB Root with progress/resume", factory=create_import)
        self._add_page("Clustering", "Configure and run clustering jobs", factory=create_clustering)
        self._add_page("Prediction Model Training", "Prepare and train prediction models", factory=create_training)
        self._add_page("Prediction Review", "Review and accept model predictions", factory=create_review)
        self._add_page("People & Groups", "Manage people records, aliases, groups", factory=create_people)
        self._add_page("Diagnostics", "Model/DB health, self-test, repair tools")
        self._add_page("Settings", "App preferences, device/worker caps, paths", factory=create_settings)

        # Default selection
        if self.nav.count():
            self.nav.setCurrentRow(0)

    def _add_page(self, name: str, placeholder: str, factory: Callable[[], QWidget] | None = None) -> None:
        """Add a nav item and register factory."""
        item = QListWidgetItem(name)
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.nav.addItem(item)

        # Create placeholder
        page = QWidget(self)
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel(f"<b>{name}</b>"), alignment=Qt.AlignmentFlag.AlignTop)
        vbox.addWidget(QLabel(placeholder))
        if factory:
            vbox.addWidget(QLabel("<i>Loading...</i>"))
        vbox.addStretch(1)
        page.setLayout(vbox)

        self.stacked.addWidget(page)
        self._pages[name] = page
        if factory:
            self._factories[name] = factory

    def _on_nav_changed(self) -> None:
        """Switch stacked widget when nav selection changes, instantiating if needed."""
        current_items: list[QListWidgetItem] = self.nav.selectedItems()
        if not current_items:
            return
        name = current_items[0].text()
        index = self.nav.row(current_items[0])
        
        # Check if we need to instantiate
        if name in self._factories:
            factory = self._factories.pop(name)
            try:
                # Show wait cursor or similar if needed, but for now just create
                real_widget = factory()
                # Replace placeholder in stack
                old_widget = self.stacked.widget(index)
                self.stacked.removeWidget(old_widget)
                self.stacked.insertWidget(index, real_widget)
                self.stacked.setCurrentIndex(index)
                self._pages[name] = real_widget
                # old_widget is garbage collected
            except Exception as exc:
                print(f"Failed to load page {name}: {exc}")
                # Keep placeholder but maybe update text?
                return

        if name in self._pages:
            self.stacked.setCurrentIndex(index)
            page = self._pages[name]
            if hasattr(page, "refresh_data"):
                try:
                    page.refresh_data()
                except Exception:
                    pass

    def _replace_context(self, new_context: AppContext) -> None:
        """Replace shared context when DB Root changes."""
        self.context = new_context

    def _ensure_people_service(self) -> PeopleService | None:
        """
        Return a live PeopleService, recreating the connection if it was closed.
        This keeps the People & Groups page resilient when the DB is reloaded.
        """
        try:
            self.context.conn.execute("SELECT 1")
            return self.context.people_service
        except Exception:
            pass

        try:
            conn = initialize_database(self.context.db_path)
            self.context.conn = conn
            self.context.people_service = PeopleService(conn, registry_path=self.context.registry_path)
            return self.context.people_service
        except Exception:
            return None
