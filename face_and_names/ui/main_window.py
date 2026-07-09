"""Main window shell for Face-and-Names v2."""

from __future__ import annotations

import logging
from typing import Callable, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from face_and_names.app_context import AppContext
from face_and_names.models.db import initialize_database
from face_and_names.services.people_service import PeopleService

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application shell with workflow-oriented navigation."""

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

        def create_home():
            return HomePage(self)

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

            confirm_delete = True
            if isinstance(self.context.config, dict):
                confirm_delete = bool(
                    self.context.config.get("ui", {}).get("confirm_delete_face", True)
                )
            return PeopleGroupsPage(
                self._ensure_people_service,
                confirm_delete=confirm_delete,
                db_path=self.context.db_path,
            )

        def create_advanced_search():
            from face_and_names.ui.advanced_search_page import AdvancedSearchPage

            return AdvancedSearchPage(self._ensure_people_service)

        def create_diagnostics():
            from face_and_names.ui.diagnostics_page import DiagnosticsPage

            return DiagnosticsPage(self.context)

        def create_settings():
            from face_and_names.ui.settings_page import SettingsPage

            return SettingsPage(self.context)

        self._add_page(
            "Home",
            "Open the recommended workflow and jump to the next task.",
            factory=create_home,
        )
        self._add_page(
            "Import",
            "Choose a DB Root and ingest photos before reviewing faces.",
            factory=create_import,
        )
        self._add_page(
            "Faces",
            "Review, filter, and assign faces in the unified workspace.",
            factory=create_faces,
        )
        self._add_page(
            "People & Groups",
            "Manage people records, aliases, groups, and assigned faces.",
            factory=create_people,
        )
        self._add_page(
            "Advanced Search",
            "Search images by name, date, and face count.",
            factory=create_advanced_search,
        )
        self._add_page(
            "Prediction Model Training",
            "Train a model from verified named faces.",
            factory=create_training,
        )
        self._add_page(
            "Advanced Prediction Review",
            "Person-specific legacy review tools; prefer Faces for routine review.",
            factory=create_review,
        )
        self._add_page(
            "Advanced Clustering",
            "Run clustering jobs and inspect clusters as an advanced workflow.",
            factory=create_clustering,
        )
        self._add_page(
            "Diagnostics",
            "Check DB, registry, model artifacts, and detector setup.",
            factory=create_diagnostics,
        )
        self._add_page(
            "Settings",
            "Edit app preferences, worker caps, and paths.",
            factory=create_settings,
        )

        # Default selection
        if self.nav.count():
            self.nav.setCurrentRow(0)

    def _add_page(
        self, name: str, placeholder: str, factory: Callable[[], QWidget] | None = None
    ) -> None:
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
                real_widget = factory()
                old_widget = self.stacked.widget(index)
                self.stacked.removeWidget(old_widget)
                self.stacked.insertWidget(index, real_widget)
                self.stacked.setCurrentIndex(index)
                self._pages[name] = real_widget
            except Exception as exc:
                LOGGER.exception("Failed to load page %s", name)
                self._show_page_load_error(name, exc, index)
                return

        if name in self._pages:
            self.stacked.setCurrentIndex(index)
            page = self._pages[name]
            if hasattr(page, "refresh_data"):
                try:
                    page.refresh_data()
                except Exception:
                    LOGGER.exception("Failed to refresh page %s", name)

    def _replace_context(self, new_context: AppContext) -> None:
        """Replace shared context when DB Root changes."""
        self.context = new_context

    def _navigate_to(self, page_name: str) -> None:
        """Select a navigation item by name."""
        for row in range(self.nav.count()):
            if self.nav.item(row).text() == page_name:
                self.nav.setCurrentRow(row)
                return

    def _show_page_load_error(self, name: str, exc: Exception, index: int) -> None:
        """Replace a failed lazy page with a visible error panel."""
        page = QWidget(self)
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"<b>{name}</b>"))
        message = QLabel(f"Could not load this page: {exc}")
        message.setWordWrap(True)
        layout.addWidget(message)
        layout.addStretch(1)
        page.setLayout(layout)
        old_widget = self.stacked.widget(index)
        self.stacked.removeWidget(old_widget)
        self.stacked.insertWidget(index, page)
        self.stacked.setCurrentIndex(index)
        self._pages[name] = page

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
            self.context.people_service = PeopleService(
                conn, registry_path=self.context.registry_path
            )
            return self.context.people_service
        except Exception:
            return None


class HomePage(QWidget):
    """Workflow-oriented landing page for returning users."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.window = window
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("<h2>Face-and-Names</h2>")
        intro = QLabel(
            "Recommended workflow: choose a DB Root, import photos, review detected faces, "
            "maintain people, then train and review predictions."
        )
        intro.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(intro)

        steps = [
            ("1. Import photos", "Import"),
            ("2. Review faces", "Faces"),
            ("3. Manage people", "People & Groups"),
            ("4. Train model", "Prediction Model Training"),
            ("5. Review predictions", "Faces"),
        ]
        for label, target in steps:
            button = QPushButton(label)
            button.setMinimumHeight(34)
            button.clicked.connect(
                lambda checked=False, page=target: self.window._navigate_to(page)
            )
            layout.addWidget(button)

        note = QLabel(
            "Advanced clustering, advanced prediction review, search, diagnostics, and settings "
            "are available from the navigation when needed."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        self.setLayout(layout)
