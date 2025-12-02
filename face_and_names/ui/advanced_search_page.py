from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from face_and_names.services.advanced_search_service import (
    AdvancedSearchService,
    FilterType,
    LogicOperator,
    SearchCriterion,
)
from face_and_names.services.people_service import PeopleService
from face_and_names.ui.components.face_tile import FaceTile, FaceTileData
from face_and_names.ui.faces_page import FaceImageView

LOGGER = logging.getLogger(__name__)


class FilterRow(QWidget):
    def __init__(self, index: int, remove_callback: Callable[[QWidget], None]):
        super().__init__()
        self.index = index
        self.remove_callback = remove_callback
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        # Logic Operator (AND/OR) - hidden for first row
        self.logic_combo = QComboBox()
        self.logic_combo.addItems([op.value for op in LogicOperator])
        self.logic_combo.setFixedWidth(60)
        if index == 0:
            self.logic_combo.setVisible(False)
        self.layout.addWidget(self.logic_combo)

        # Field Selector
        self.field_combo = QComboBox()
        self.field_combo.addItems([ft.value for ft in FilterType])
        self.field_combo.currentIndexChanged.connect(self._on_field_changed)
        self.layout.addWidget(self.field_combo)

        # Value Widgets Stack
        self.value_stack = QStackedWidget()
        self.layout.addWidget(self.value_stack)

        # 1. Name Input
        self.name_widget = QWidget()
        name_layout = QHBoxLayout()
        name_layout.setContentsMargins(0, 0, 0, 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Name...")
        self.fuzzy_check = QCheckBox("Fuzzy")
        self.fuzzy_check.setChecked(True)
        name_layout.addWidget(self.name_input)
        name_layout.addWidget(self.fuzzy_check)
        self.name_widget.setLayout(name_layout)
        self.value_stack.addWidget(self.name_widget)

        # 2. Date Range
        self.date_widget = QWidget()
        date_layout = QHBoxLayout()
        date_layout.setContentsMargins(0, 0, 0, 0)
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setDate(QDate.currentDate().addYears(-1))
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setDate(QDate.currentDate())
        date_layout.addWidget(QLabel("From:"))
        date_layout.addWidget(self.date_start)
        date_layout.addWidget(QLabel("To:"))
        date_layout.addWidget(self.date_end)
        self.date_widget.setLayout(date_layout)
        self.value_stack.addWidget(self.date_widget)

        # 3. Person Count
        self.count_widget = QWidget()
        count_layout = QHBoxLayout()
        count_layout.setContentsMargins(0, 0, 0, 0)
        self.count_op = QComboBox()
        self.count_op.addItems(["=", ">", "<", ">=", "<="])
        self.count_spin = QSpinBox()
        self.count_spin.setRange(0, 100)
        count_layout.addWidget(self.count_op)
        count_layout.addWidget(self.count_spin)
        self.count_widget.setLayout(count_layout)
        self.value_stack.addWidget(self.count_widget)

        # Remove Button
        self.remove_btn = QPushButton("X")
        self.remove_btn.setFixedWidth(30)
        self.remove_btn.clicked.connect(lambda: self.remove_callback(self))
        self.layout.addWidget(self.remove_btn)

    def _on_field_changed(self, index: int):
        # Map combo index to stack index (assuming same order as FilterType enum)
        # FilterType: NAME_FUZZY (0), DATE_RANGE (1), PERSON_COUNT (2)
        self.value_stack.setCurrentIndex(index)

    def get_criterion(self) -> SearchCriterion:
        ft = FilterType(self.field_combo.currentText())
        op = LogicOperator(self.logic_combo.currentText())
        value = {}

        if ft == FilterType.NAME_FUZZY:
            value = {
                "name": self.name_input.text(),
                "threshold": 0.6 if self.fuzzy_check.isChecked() else 1.0,
            }
        elif ft == FilterType.DATE_RANGE:
            s = self.date_start.date()
            e = self.date_end.date()
            value = {
                "start": date(s.year(), s.month(), s.day()),
                "end": date(e.year(), e.month(), e.day()),
            }
        elif ft == FilterType.PERSON_COUNT:
            value = {"operator": self.count_op.currentText(), "count": self.count_spin.value()}

        return SearchCriterion(filter_type=ft, operator=op, value=value)


class AdvancedSearchPage(QWidget):
    def __init__(self, service_provider: Callable[[], PeopleService | None]):
        super().__init__()
        self._service_provider = service_provider
        self._search_service: Optional[AdvancedSearchService] = None

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Query Builder Area
        self.query_scroll = QScrollArea()
        self.query_scroll.setWidgetResizable(True)
        self.query_scroll.setMaximumHeight(250)
        self.query_widget = QWidget()
        self.query_layout = QVBoxLayout()
        self.query_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.query_widget.setLayout(self.query_layout)
        self.query_scroll.setWidget(self.query_widget)
        self.layout.addWidget(self.query_scroll)

        # Controls
        controls_layout = QHBoxLayout()
        self.add_btn = QPushButton("+ Add Criteria")
        self.add_btn.clicked.connect(self._add_row)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._perform_search)
        controls_layout.addWidget(self.add_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(self.search_btn)
        self.layout.addLayout(controls_layout)

        # Results Area
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_inner = QWidget()
        self.results_grid = QGridLayout()
        self.results_grid.setSpacing(10)
        self.results_inner.setLayout(self.results_grid)
        self.results_scroll.setWidget(self.results_inner)
        self.layout.addWidget(self.results_scroll)

        self.status_label = QLabel("Ready")
        self.layout.addWidget(self.status_label)

        # Initialize with one row
        self._add_row()

    def _get_service(self) -> AdvancedSearchService | None:
        if self._search_service:
            return self._search_service

        people_service = self._service_provider()
        if people_service:
            self._search_service = AdvancedSearchService(people_service)
            return self._search_service
        return None

    def _add_row(self):
        index = self.query_layout.count()
        row = FilterRow(index, self._remove_row)
        self.query_layout.addWidget(row)

    def _remove_row(self, row: QWidget):
        if self.query_layout.count() > 1:
            row.deleteLater()
            self.query_layout.removeWidget(row)
            # Re-index rows to ensure logic combo visibility is correct?
            # Actually, just ensuring the first remaining row hides logic combo is enough.
            # For simplicity, we won't re-index dynamically here, but we should ensure
            # at least one row remains or handle empty state.
        else:
            self.status_label.setText("Cannot remove the last row.")

    def _perform_search(self):
        service = self._get_service()
        if not service:
            self.status_label.setText("Service unavailable.")
            return

        criteria = []
        for i in range(self.query_layout.count()):
            widget = self.query_layout.itemAt(i).widget()
            if isinstance(widget, FilterRow):
                criteria.append(widget.get_criterion())

        results = service.search(criteria)
        self._display_results(results)

    def _display_results(self, results):
        # Clear grid
        while self.results_grid.count():
            item = self.results_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.status_label.setText(f"Found {len(results)} images.")

        max_cols = 5
        for idx, res in enumerate(results):
            # We reuse FaceTile but adapt it for generic image
            # Or create a simple ImageTile. Let's reuse FaceTile for consistency if possible,
            # but FaceTile expects face data.
            # Let's create a simplified tile here or mock FaceTileData.

            tile = FaceTile(
                FaceTileData(
                    face_id=res.image_id,  # Using image_id as ID
                    person_id=None,
                    person_name=None,
                    predicted_person_id=None,
                    predicted_name=None,
                    confidence=None,
                    crop=res.thumbnail_blob,
                ),
                delete_face=lambda _: None,
                assign_person=lambda *_: None,
                list_persons=lambda: [],
                create_person=lambda *_: 0,
                rename_person=lambda *_: None,
                open_original=lambda _, path=res.relative_path: self._open_original(path),
                confirm_delete=False,
            )
            # Override label
            tile.assigned_label.setText(res.relative_path)

            row, col = divmod(idx, max_cols)
            self.results_grid.addWidget(tile, row, col)

    def _open_original(self, relative_path: str) -> None:
        # Try to resolve DB root from the people service connection
        service = self._get_service()
        if service is None:
            return
        try:
            db_path = service.people_service.conn.execute("PRAGMA database_list").fetchone()[2]
            base = Path(db_path).parent
            img_path = base / relative_path
        except Exception:
            img_path = Path(relative_path)
        if not img_path.exists():
            QMessageBox.warning(self, "Image missing", f"File not found: {img_path}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(str(img_path))
        view = FaceImageView()
        from PyQt6.QtGui import QPixmap

        pixmap = QPixmap(str(img_path))
        view.show_image(pixmap, [])
        layout = QVBoxLayout()
        layout.addWidget(view)
        dialog.setLayout(layout)
        dialog.resize(800, 600)
        dialog.exec()
