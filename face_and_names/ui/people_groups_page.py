"""
People & Groups page (people list + assigned faces with pagination).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from face_and_names.services.people_groups_controller import PeopleGroupsController
from face_and_names.services.people_service import PeopleService
from face_and_names.ui.components.face_tile import FaceTile, FaceTileData
from face_and_names.ui.faces_page import FaceImageView


def _person_label(person: dict) -> str:
    first = (person.get("first_name") or "").strip()
    last = (person.get("last_name") or "").strip()
    short = (person.get("short_name") or "").strip()
    parts = []
    if short:
        parts.append(f"Short: {short}")
    if first or last:
        parts.append(f"Name: {first} {last}".strip())
    display = person.get("display_name") or person.get("primary_name") or ""
    parts.append(f"Display: {display}")
    return " | ".join(parts)


def _person_sort_key(person: dict) -> str:
    return (
        person.get("short_name") or person.get("display_name") or person.get("primary_name") or ""
    ).casefold()


SORT_LABELS = {
    "date_desc": "Photo date: latest first",
    "date_asc": "Photo date: oldest first",
}

VIEW_MODE_FACES = "faces"
VIEW_MODE_IMAGES = "images"


class PeopleGroupsPage(QWidget):
    """People page showing a sortable list of people and their faces."""

    PAGE_SIZE = 20

    def __init__(
        self,
        service_provider: Callable[[], PeopleService | None],
        *,
        confirm_delete: bool = True,
        db_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_provider = service_provider
        self._controller: PeopleGroupsController | None = None
        self.confirm_delete = confirm_delete
        self.db_path = db_path
        self.people_list = QListWidget()
        self.people_list.setMinimumWidth(260)
        self.faces_area = QScrollArea()
        self.faces_area.setWidgetResizable(True)
        self.faces_inner = QWidget()
        self.faces_layout = QGridLayout()
        self.faces_layout.setContentsMargins(8, 8, 8, 8)
        self.faces_layout.setSpacing(12)
        self.faces_inner.setLayout(self.faces_layout)
        self.faces_area.setWidget(self.faces_inner)
        self.timeline_label = QLabel("")
        self.timeline_row = QHBoxLayout()
        self.timeline_row.setContentsMargins(0, 0, 0, 0)
        self.timeline_row.setSpacing(6)
        self.timeline_widget = QWidget()
        self.timeline_widget.setLayout(self.timeline_row)
        self.timeline_selected_month: tuple[int, int] | None = None
        self.status = QLabel("Select a person to view their faces and photos.")
        self.page_label = QLabel("Page 1/1")
        self.prev_btn = QPushButton("<")
        self.next_btn = QPushButton(">")
        self.from_date = QDateEdit(calendarPopup=True)
        self.to_date = QDateEdit(calendarPopup=True)
        self.reset_dates_btn = QPushButton("Reset dates")
        for widget in (self.from_date, self.to_date):
            widget.setDisplayFormat("yyyy-MM-dd")
            widget.setMinimumWidth(110)
        self.sort_combo = QComboBox()
        for key, label in SORT_LABELS.items():
            self.sort_combo.addItem(label, userData=key)
        self.sort_combo.setCurrentIndex(0)
        self.faces_mode_btn = QRadioButton("Face crops")
        self.images_mode_btn = QRadioButton("Original photos")
        self.faces_mode_btn.setChecked(True)
        self.people: list[dict] = []
        self.current_person_id: int | None = None
        self.current_page = 0
        self.current_tiles: list[FaceTile] = []
        self.sort_key = self.sort_combo.currentData()
        self.view_mode = VIEW_MODE_FACES
        self.date_range: tuple[datetime, datetime] | None = None

        self._build_ui()
        self._refresh_people()

    def _service(self) -> PeopleService | None:
        return self._service_provider()

    def _controller_service(self) -> PeopleGroupsController | None:
        service = self._service()
        if service is None:
            return None
        if self._controller is None or self._controller.conn is not service.conn:
            db_root = self.db_path.parent if self.db_path else Path.cwd()
            self._controller = PeopleGroupsController(service.conn, db_root)
        return self._controller

    def _build_ui(self) -> None:
        left = QVBoxLayout()
        left.addWidget(QLabel("<h2>People & Groups</h2>"))
        left.addWidget(QLabel("People sorted by short or display name"))
        left.addWidget(self.people_list, stretch=1)

        faces_controls = QHBoxLayout()
        faces_controls.addStretch(1)
        faces_controls.addWidget(QLabel("Show:"))
        faces_controls.addWidget(self.faces_mode_btn)
        faces_controls.addWidget(self.images_mode_btn)
        faces_controls.addWidget(QLabel("Date from:"))
        faces_controls.addWidget(self.from_date)
        faces_controls.addWidget(QLabel("to"))
        faces_controls.addWidget(self.to_date)
        faces_controls.addWidget(self.reset_dates_btn)
        faces_controls.addWidget(QLabel("Sort:"))
        faces_controls.addWidget(self.sort_combo)
        faces_controls.addWidget(self.prev_btn)
        faces_controls.addWidget(self.page_label)
        faces_controls.addWidget(self.next_btn)
        faces_controls.addStretch(1)

        right = QVBoxLayout()
        right.addWidget(self.timeline_label)
        right.addWidget(self.timeline_widget)
        right.addLayout(faces_controls)
        right.addWidget(self.faces_area, stretch=1)
        right.addWidget(self.status)

        root = QHBoxLayout()
        root.addLayout(left, stretch=0)
        root.addLayout(right, stretch=1)
        self.setLayout(root)

        self.people_list.itemSelectionChanged.connect(self._on_person_selected)
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self.faces_mode_btn.toggled.connect(self._on_mode_changed)
        self.images_mode_btn.toggled.connect(self._on_mode_changed)
        self.timeline_widget.mouseDoubleClickEvent = (
            lambda event: self._on_timeline_double_click(event)  # type: ignore[assignment]
        )
        self.from_date.dateChanged.connect(self._on_date_changed)
        self.to_date.dateChanged.connect(self._on_date_changed)
        self.reset_dates_btn.clicked.connect(self._on_reset_dates)

    def _refresh_people(self) -> None:
        service = self._service()
        if service is None:
            return
        try:
            people = service.list_people()
        except Exception:
            return
        people = sorted(people, key=_person_sort_key)
        self.people = people
        self.people_list.clear()
        for person in people:
            item = QListWidgetItem(_person_label(person))
            item.setData(Qt.ItemDataRole.UserRole, person.get("id"))
            self.people_list.addItem(item)
        if people:
            self.people_list.setCurrentRow(0)
        else:
            self._clear_faces()
            self.status.setText("No people found.")

    def showEvent(self, event) -> None:  # type: ignore[override]
        self._refresh_people()
        return super().showEvent(event)

    def _on_person_selected(self) -> None:
        items = self.people_list.selectedItems()
        self.timeline_selected_month = None  # reset date filter when switching people
        self.current_person_id = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        self.current_page = 0
        self.date_range = None
        self._load_faces()

    def _prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self._load_faces()

    def _next_page(self) -> None:
        self.current_page += 1
        self._load_faces()

    def _on_sort_changed(self) -> None:
        self.sort_key = self.sort_combo.currentData()
        self.current_page = 0
        self._load_faces()

    def _on_mode_changed(self) -> None:
        self.view_mode = VIEW_MODE_IMAGES if self.images_mode_btn.isChecked() else VIEW_MODE_FACES
        self.current_page = 0
        self._load_faces()

    def _on_date_changed(self) -> None:
        if self.from_date.date().isValid() and self.to_date.date().isValid():
            start = datetime(
                self.from_date.date().year(),
                self.from_date.date().month(),
                self.from_date.date().day(),
            )
            end = datetime(
                self.to_date.date().year(),
                self.to_date.date().month(),
                self.to_date.date().day(),
            )
            self.date_range = (start, end)
            self.current_page = 0
            self.timeline_selected_month = None
            self._load_faces()

    def _on_reset_dates(self) -> None:
        self.timeline_selected_month = None
        self._set_date_range_to_bounds()
        self.current_page = 0
        self._load_faces()

    def _clear_faces(self) -> None:
        self.current_tiles = []
        while self.faces_layout.count():
            item = self.faces_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _load_faces(self) -> None:
        self._clear_faces()
        person_id = self.current_person_id
        if person_id is None:
            self.status.setText("Select a person to view faces.")
            return
        # Ensure we have a date range when filtering
        if self.date_range is None:
            self._set_date_range_to_bounds()
        if self.view_mode == VIEW_MODE_IMAGES:
            rows = self._fetch_images(
                person_id=person_id, limit=self.PAGE_SIZE, offset=self.current_page * self.PAGE_SIZE
            )
            total = self._count_images(person_id)
        else:
            rows = self._fetch_faces(
                person_id=person_id, limit=self.PAGE_SIZE, offset=self.current_page * self.PAGE_SIZE
            )
            total = self._count_faces(person_id)
        total_pages = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)
            if self.view_mode == VIEW_MODE_IMAGES:
                rows = self._fetch_images(
                    person_id=person_id,
                    limit=self.PAGE_SIZE,
                    offset=self.current_page * self.PAGE_SIZE,
                )
            else:
                rows = self._fetch_faces(
                    person_id=person_id,
                    limit=self.PAGE_SIZE,
                    offset=self.current_page * self.PAGE_SIZE,
                )
        self.page_label.setText(f"Page {self.current_page + 1}/{total_pages}")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)
        if not rows:
            self.status.setText("No faces assigned to this person.")
            self._render_timeline([], None, None)
            return

        max_cols = 4
        for idx, row in enumerate(rows):
            service = self._service()
            if self.view_mode == VIEW_MODE_IMAGES:
                tile = self._build_image_tile(row, service)
            else:
                tile = self._build_face_tile(row, service)
            row_idx, col_idx = divmod(idx, max_cols)
            self.faces_layout.addWidget(tile, row_idx, col_idx, alignment=Qt.AlignmentFlag.AlignTop)
            self.current_tiles.append(tile)
        label = "faces" if self.view_mode == VIEW_MODE_FACES else "images"
        self.status.setText(f"Showing {len(rows)} {label} (Total: {total})")
        # Timeline based on images containing this person
        dates = self._collect_dates_for_person(person_id)
        if self.date_range is None:
            self._set_date_range_to_bounds(dates)
        self._render_timeline(dates, min(dates) if dates else None, max(dates) if dates else None)

    def _build_face_tile(self, row, service: PeopleService | None) -> FaceTile:
        tile = FaceTile(
            FaceTileData(
                face_id=row.face_id,
                person_id=row.person_id,
                person_name=row.person_name,
                predicted_person_id=row.predicted_person_id,
                predicted_name=row.predicted_name,
                confidence=row.confidence,
                crop=row.crop,
            ),
            delete_face=self._delete_face,
            assign_person=self._assign_person,
            list_persons=self._list_people,
            create_person=lambda first, last, short, service=service: service.create_person(  # type: ignore[arg-type,union-attr]
                first, last, short
            )
            if service
            else 0,
            rename_person=service.rename_person if service else lambda *_: None,  # type: ignore[arg-type]
            open_original=self._open_original_image,
            confirm_delete=self.confirm_delete,
        )
        shot = self._shot_date_for_face(row.face_id)
        if shot:
            label = tile.assigned_label.text() or "(unnamed)"
            tile.assigned_label.setText(f"{label}\n{shot.date()}")
        return tile

    def _build_image_tile(self, row, service: PeopleService | None) -> FaceTile:
        # Reuse FaceTile visuals but show the whole image thumb with no predicted info.
        tile = FaceTile(
            FaceTileData(
                face_id=row.image_id,  # image_id repurposed
                person_id=row.person_id,
                person_name=row.person_name,
                predicted_person_id=None,
                predicted_name=None,
                confidence=None,
                crop=row.thumb,
            ),
            delete_face=self._delete_image if service else lambda _: None,
            assign_person=lambda *_: None,
            list_persons=self._list_people,
            create_person=lambda *_: 0,
            rename_person=lambda *_: None,
            open_original=lambda *_: self._open_original_image_from_path(row.relative_path),
            confirm_delete=self.confirm_delete,
        )
        shot = self._shot_date_for_image(row.image_id)
        if shot:
            label = tile.assigned_label.text() or "(unnamed)"
            tile.assigned_label.setText(f"{label}\n{shot.date()}")
        return tile

    def _after_change(self) -> None:
        # Refresh faces and people counts when face data changes
        self._refresh_people()
        self._load_faces()

    def _delete_face(self, face_id: int) -> None:
        controller = self._controller_service()
        if controller is None:
            return
        controller.delete_face(face_id)

    def _delete_image(self, image_id: int) -> None:
        controller = self._controller_service()
        if controller is None:
            return
        controller.delete_image(image_id)

    def _assign_person(self, face_id: int, person_id: int | None) -> None:
        controller = self._controller_service()
        if controller is None:
            return
        controller.assign_person(face_id, person_id)

    def _list_people(self) -> list[dict]:
        service = self._service()
        if service is None:
            return []
        return sorted(service.list_people(), key=_person_sort_key)

    def _count_faces(self, person_id: int) -> int:
        controller = self._controller_service()
        if controller is None:
            return 0
        start, end = self._active_date_range()
        return controller.count_faces(person_id, start, end)

    def _count_images(self, person_id: int) -> int:
        controller = self._controller_service()
        if controller is None:
            return 0
        start, end = self._active_date_range()
        return controller.count_images(person_id, start, end)

    def _fetch_faces(self, person_id: int, limit: int, offset: int) -> list:
        controller = self._controller_service()
        if controller is None:
            return []
        start, end = self._active_date_range()
        return controller.fetch_faces(person_id, limit, offset, self.sort_key, start, end)

    def _fetch_images(self, person_id: int, limit: int, offset: int) -> list:
        controller = self._controller_service()
        if controller is None:
            return []
        start, end = self._active_date_range()
        return controller.fetch_images(person_id, limit, offset, self.sort_key, start, end)

    def _open_original_image(self, face_id: int) -> None:
        controller = self._controller_service()
        if controller is None:
            return
        original = controller.original_face_image(face_id)
        if original is None:
            return
        img_path = original.image_path
        if not img_path.exists():
            QMessageBox.warning(self, "Image missing", f"File not found: {img_path}")
            return
        from PyQt6.QtGui import QPixmap  # local import to avoid circular issues

        pix = QPixmap(str(img_path))
        window = QDialog(self)
        window.setWindowTitle("Original image")
        view = FaceImageView()
        view.show_image(pix, [original.bbox_rel])
        layout = QVBoxLayout()
        layout.addWidget(view)
        window.setLayout(layout)
        window.resize(800, 600)
        window.exec()

    def _open_original_image_from_path(self, relative_path: str) -> None:
        controller = self._controller_service()
        if controller is None:
            return
        img_path = controller.original_image_path(relative_path)
        if not img_path.exists():
            QMessageBox.warning(self, "Image missing", f"File not found: {img_path}")
            return
        from PyQt6.QtGui import QPixmap  # local import to avoid circular issues

        pix = QPixmap(str(img_path))
        window = QDialog(self)
        window.setWindowTitle("Original image")
        view = FaceImageView()
        view.show_image(pix, [])
        layout = QVBoxLayout()
        layout.addWidget(view)
        window.setLayout(layout)
        window.resize(800, 600)
        window.exec()

    # Timeline helpers ---------------------------------------------------
    def _collect_dates_for_person(self, person_id: int) -> list[datetime]:
        controller = self._controller_service()
        if controller is None:
            return []
        return controller.collect_dates_for_person(person_id)

    def _shot_date_for_face(self, face_id: int) -> datetime | None:
        controller = self._controller_service()
        if controller is None:
            return None
        return controller.shot_date_for_face(face_id)

    def _shot_date_for_image(self, image_id: int) -> datetime | None:
        controller = self._controller_service()
        if controller is None:
            return None
        return controller.shot_date_for_image(image_id)

    # Date range helpers -------------------------------------------------
    def _set_date_range_to_bounds(self, dates: list[datetime] | None = None) -> None:
        dates = dates or self._collect_dates_for_person(self.current_person_id or -1)
        if dates:
            start = min(dates)
            end = max(dates)
        else:
            start = datetime(1900, 1, 1)
            end = datetime.combine(date.today(), datetime.min.time())
        self.date_range = (start, end)
        self.from_date.setDate(QDate(start.year, start.month, start.day))
        self.to_date.setDate(QDate(end.year, end.month, end.day))

    def _set_month_range(self, year: int, month: int) -> None:
        last_day = monthrange(year, month)[1]
        start = datetime(year, month, 1)
        end = datetime(year, month, last_day)
        self.date_range = (start, end)
        self.from_date.setDate(QDate(start.year, start.month, start.day))
        self.to_date.setDate(QDate(end.year, end.month, end.day))

    def _active_date_range(self) -> tuple[datetime | None, datetime | None]:
        if self.timeline_selected_month:
            year, month = self.timeline_selected_month
            return datetime(year, month, 1), datetime(year, month, monthrange(year, month)[1])
        if self.date_range:
            return self.date_range
        return None, None

    def _render_timeline(
        self, dates: list[datetime], min_date: datetime | None, max_date: datetime | None
    ) -> None:
        # Clear existing
        while self.timeline_row.count():
            item = self.timeline_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not dates or not min_date or not max_date:
            self.timeline_label.setText("No date metadata available for this person.")
            return
        self.timeline_label.setText(
            f"Photos from {min_date.date()} to {max_date.date()} (by month)"
        )
        # Aggregate by month
        counts: dict[tuple[int, int], int] = {}
        for dt_obj in dates:
            key = (dt_obj.year, dt_obj.month)
            counts[key] = counts.get(key, 0) + 1
        max_count = max(counts.values()) if counts else 1
        sorted_keys = sorted(counts.keys())
        last_year = None
        for year, month in sorted_keys:
            if last_year != year:
                year_lbl = QLabel(str(year))
                year_lbl.setStyleSheet("color: #888; font-size: 11px;")
                self.timeline_row.addWidget(year_lbl)
                last_year = year
            count = counts[(year, month)]
            size = 12 + int(28 * (count / max_count))  # scale circle 12-40px
            circle = QLabel(f"{month:02d}")
            circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            circle.setFixedSize(size, size)
            circle.setToolTip(f"{year}-{month:02d}: {count} photos")
            is_selected = self.timeline_selected_month == (year, month)
            bg = "#5c8df6" if not is_selected else "#f58f5c"
            circle.setStyleSheet(
                "border-radius: %dpx; background: %s; color: white; font-size: 11px; border: 1px solid #ddd;"
                % (size // 2, bg)
            )
            circle.mousePressEvent = self._make_circle_click_handler(year, month)  # type: ignore[assignment]
            self.timeline_row.addWidget(circle)

    def _make_circle_click_handler(self, year: int, month: int):
        def handler(event):
            # Toggle selection; double-click anywhere clears filter
            if event.button() == Qt.MouseButton.LeftButton:
                if self.timeline_selected_month == (year, month):
                    self.timeline_selected_month = None
                    self.date_range = None
                else:
                    self.timeline_selected_month = (year, month)
                    self._set_month_range(year, month)
                self.current_page = 0
                self._load_faces()
            event.accept()

        return handler

    def _on_timeline_double_click(self, event) -> None:
        self.timeline_selected_month = None
        self.date_range = None
        self._set_date_range_to_bounds()
        self.current_page = 0
        self._load_faces()
