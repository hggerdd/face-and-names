"""
FaceTile component (PyQt6).

DESIGN / PLAN
- UI tech: PyQt6 widgets. Component lives under `ui/components` and can be embedded in grids/lists/tables via parent layouts.
- Name: FaceTile.
- State: keeps internal `selected` flag; toggled on left-click; exposed via signals and `is_selected()`.
- Visual: image container with overlayed predicted name (bottom), trash icon (top-right), assigned name label below image.
  Deselected state renders grayscale/lightened version of the pixmap.
- Behaviour/callbacks (injected via callables):
    * delete_face(face_id) -> None
    * assign_person(face_id, person_id) -> None
    * list_persons() -> list[dict{id, primary_name}]
    * create_person(name) -> int
    * rename_person(person_id, new_name) -> None
    * open_original(face_id) -> None
- Interactions:
    * Single-click toggles selection, emits selectionChanged(face_id, selected).
    * Trash click -> confirm dialog -> delete_face + deleteCompleted(face_id).
    * Double-click predicted name -> assign predicted_person_id as person_id, emit personAssigned.
    * Double-click assigned name -> person menu (existing persons, add new, rename current), emit personAssigned/personCreated/personRenamed.
    * Right-click on image -> open_original(face_id).
- Integration flexibility: signals allow parent views to react without tight coupling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QContextMenuEvent, QImage, QMouseEvent, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QListWidget,
    QPushButton,
    QDialogButtonBox,
    QDialog,
)


@dataclass
class FaceTileData:
    face_id: int
    person_id: int | None
    person_name: str | None
    predicted_person_id: int | None
    predicted_name: str | None
    confidence: float | None
    crop: bytes


class FaceTile(QWidget):
    selectionChanged = pyqtSignal(int, bool)
    deleteCompleted = pyqtSignal(int)
    personAssigned = pyqtSignal(int, object)
    personRenamed = pyqtSignal(int, str)
    personCreated = pyqtSignal(int, str)
    openOriginalRequested = pyqtSignal(int)

    def __init__(
        self,
        data: FaceTileData,
        *,
        delete_face: Callable[[int], None],
        assign_person: Callable[[int, int | None], None],
        list_persons: Callable[[], Iterable[dict]],
        create_person: Callable[[str], int],
        rename_person: Callable[[int, str], None],
        open_original: Callable[[int], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.data = data
        self.delete_face_cb = delete_face
        self.assign_person_cb = assign_person
        self.list_persons_cb = list_persons
        self.create_person_cb = create_person
        self.rename_person_cb = rename_person
        self.open_original_cb = open_original
        self.selected = True
        self._orig_pixmap: QPixmap | None = None

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()
        self._bind(data)

    def _build_ui(self) -> None:
        self.image_container = QFrame()
        self.image_container.setFrameShape(QFrame.Shape.StyledPanel)
        self.image_container.setStyleSheet("QFrame { background: #111; }")
        self.image_container.setFixedHeight(240)
        img_layout = QVBoxLayout()
        img_layout.setContentsMargins(4, 4, 4, 4)
        img_layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.addStretch(1)
        self.delete_btn = QToolButton()
        self.delete_btn.setText("🗑")
        self.delete_btn.setAutoRaise(True)
        self.delete_btn.setToolTip("Delete face")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        top_row.addWidget(self.delete_btn)
        img_layout.addLayout(top_row)

        self.image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(140, 140)
        self.image_label.setScaledContents(False)
        img_layout.addWidget(self.image_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.pred_label = QLabel("", alignment=Qt.AlignmentFlag.AlignLeft)
        self.pred_label.setStyleSheet("color: #eee; background: rgba(0,0,0,0.55); padding: 2px 4px;")
        self.pred_label.mouseDoubleClickEvent = lambda event: self._assign_predicted()  # type: ignore[assignment]
        img_layout.addWidget(self.pred_label, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        self.image_container.setLayout(img_layout)

        self.assigned_label = QLabel("", alignment=Qt.AlignmentFlag.AlignCenter)
        self.assigned_label.setStyleSheet("font-weight: 600;")
        self.assigned_label.mouseDoubleClickEvent = lambda event: self._open_person_menu()  # type: ignore[assignment]

        root = QVBoxLayout()
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        root.addWidget(self.image_container)
        root.addWidget(self.assigned_label)
        self.setLayout(root)

    def _bind(self, data: FaceTileData) -> None:
        self.data = data
        self.assigned_label.setText(data.person_name or "(unnamed)")
        if data.predicted_name:
            conf = f"{data.confidence:.2f}" if data.confidence is not None else "-"
            self.pred_label.setText(f"{data.predicted_name} ({conf})")
        else:
            self.pred_label.setText("")
        pixmap = QPixmap()
        if pixmap.loadFromData(data.crop):
            self._orig_pixmap = pixmap
            self._apply_selection_visual()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_selected()
        elif event.button() == Qt.MouseButton.RightButton:
            self._open_original()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            if self.pred_label.geometry().adjusted(0, 0, 0, 10).contains(pos, proper=False):
                self._assign_predicted()
            elif self.assigned_label.geometry().adjusted(0, 0, 0, 10).contains(pos, proper=False):
                self._open_person_menu()
            else:
                self._open_person_menu()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._open_original()
        event.accept()

    def toggle_selected(self) -> None:
        self.selected = not self.selected
        self._apply_selection_visual()
        if self.data:
            self.selectionChanged.emit(self.data.face_id, self.selected)

    def is_selected(self) -> bool:
        return self.selected

    def _apply_selection_visual(self) -> None:
        if not self._orig_pixmap:
            return
        if self.selected:
            scaled = self._orig_pixmap.scaled(
                160, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
            self.image_label.setGraphicsEffect(None)
        else:
            img: QImage = self._orig_pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
            pix = QPixmap.fromImage(img).scaled(
                160, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(pix)

    def _on_delete_clicked(self) -> None:
        if not self.data:
            return
        ret = QMessageBox.question(
            self, "Delete face", "Delete this face and all references?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            self.delete_face_cb(self.data.face_id)
            self.deleteCompleted.emit(self.data.face_id)
        except Exception as exc:  # pragma: no cover - UI safety
            QMessageBox.critical(self, "Delete failed", str(exc))

    def _assign_predicted(self) -> None:
        if not self.data or self.data.predicted_person_id is None:
            return
        try:
            self.assign_person_cb(self.data.face_id, self.data.predicted_person_id)
            self.personAssigned.emit(self.data.face_id, self.data.predicted_person_id)
            # update assigned label immediately
            if self.data.predicted_name:
                self.assigned_label.setText(self.data.predicted_name)
                self.data.person_id = self.data.predicted_person_id
                self.data.person_name = self.data.predicted_name
        except Exception as exc:  # pragma: no cover - UI safety
            QMessageBox.critical(self, "Assign failed", str(exc))

    def _open_person_menu(self) -> None:
        if not self.data:
            return
        persons = list(self.list_persons_cb())
        dlg = PersonSelectDialog(
            persons=persons,
            create_person=self.create_person_cb,
            rename_person=self.rename_person_cb,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected_id = dlg.selected_person_id
            if selected_id is not None:
                self._assign_person(selected_id)

    def _assign_person(self, person_id: int) -> None:
        if not self.data:
            return
        try:
            self.assign_person_cb(self.data.face_id, person_id)
            self.personAssigned.emit(self.data.face_id, person_id)
            # refresh label to selected name using latest display_name
            name = self._resolve_display_name(person_id)
            if name:
                self.assigned_label.setText(name)
                self.data.person_id = person_id
                self.data.person_name = name
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "Assign failed", str(exc))

    def _add_person(self) -> None:
        if not self.data:
            return
        name, ok = QInputDialog.getText(self, "New person", "Name:")
        if not ok or not name.strip():
            return
        try:
            first, last = self._split_name(name.strip())
            pid = self.create_person_cb(first, last, None)
            self.personCreated.emit(pid, name.strip())
            self._assign_person(pid)
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "Create failed", str(exc))

    def _rename_person(self) -> None:
        if not self.data or self.data.person_id is None:
            return
        current = self._resolve_display_name(self.data.person_id) or ""
        first_last = current.split(" ", 1)
        first_default = first_last[0] if first_last else ""
        last_default = first_last[1] if len(first_last) > 1 else ""
        first_name, ok1 = QInputDialog.getText(self, "Rename person", "First name:", text=first_default)
        if not ok1:
            return
        last_name, ok2 = QInputDialog.getText(self, "Rename person", "Last name:", text=last_default)
        if not ok2:
            return
        short_name, ok3 = QInputDialog.getText(self, "Rename person", "Short name (optional):", text=current)
        if not ok3:
            return
        try:
            self.rename_person_cb(self.data.person_id, first_name.strip(), last_name.strip(), short_name.strip() or None)
            self.personRenamed.emit(self.data.person_id, short_name.strip() or f"{first_name.strip()} {last_name.strip()}".strip())
            name = self._resolve_display_name(self.data.person_id)
            if name:
                self.assigned_label.setText(name)
                self.data.person_name = name
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "Rename failed", str(exc))

    def _open_original(self) -> None:
        if not self.data:
            return
        if self.open_original_cb:
            self.open_original_cb(self.data.face_id)
        else:
            self.openOriginalRequested.emit(self.data.face_id)

    def _resolve_display_name(self, person_id: int) -> str | None:
        for person in self.list_persons_cb():
            if person.get("id") == person_id:
                return person.get("display_name") or person.get("primary_name")
        return None


class PersonSelectDialog(QDialog):
    """Dialog for selecting/adding/renaming persons by ID."""

    def __init__(
        self,
        persons: list[dict],
        create_person: Callable[[str, str, str | None], int],
        rename_person: Callable[[int, str, str, str | None], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Assign person")
        self.persons = persons
        self.create_person_cb = create_person
        self.rename_person_cb = rename_person
        self.selected_person_id: int | None = None

        self.list_widget = QListWidget()
        self._refresh_list()

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_person)
        rename_btn = QPushButton("Rename")
        rename_btn.clicked.connect(self._rename_person)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rename_btn)
        btn_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Choose an existing person:"))
        layout.addWidget(self.list_widget)
        layout.addLayout(btn_row)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.resize(320, 360)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for person in self.persons:
            self.list_widget.addItem(f"{person['primary_name']} (ID {person['id']})")

    def _selected_index(self) -> int:
        return self.list_widget.currentRow()

    def _add_person(self) -> None:
        name, ok = QInputDialog.getText(self, "Add person", "Name:")
        if not ok or not name.strip():
            return
        first, last = self._split_name(name.strip())
        pid = self.create_person_cb(first, last, None)
        display = name.strip()
        self.persons.append({"id": pid, "primary_name": display, "display_name": display})
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self.persons) - 1)

    def _rename_person(self) -> None:
        idx = self._selected_index()
        if idx < 0 or idx >= len(self.persons):
            return
        current = self.persons[idx].get("display_name") or self.persons[idx]["primary_name"]
        parts = current.split(" ", 1)
        first_default = parts[0] if parts else ""
        last_default = parts[1] if len(parts) > 1 else ""
        first_name, ok1 = QInputDialog.getText(self, "Rename person", "First name:", text=first_default)
        if not ok1:
            return
        last_name, ok2 = QInputDialog.getText(self, "Rename person", "Last name:", text=last_default)
        if not ok2:
            return
        short_name, ok3 = QInputDialog.getText(self, "Rename person", "Short name (optional):", text=current)
        if not ok3:
            return
        pid = self.persons[idx]["id"]
        self.rename_person_cb(pid, first_name.strip(), last_name.strip(), short_name.strip() or None)
        display = short_name.strip() or f"{first_name.strip()} {last_name.strip()}".strip()
        self.persons[idx]["primary_name"] = display
        self.persons[idx]["display_name"] = display
        self._refresh_list()
        self.list_widget.setCurrentRow(idx)

    def _accept(self) -> None:
        idx = self._selected_index()
        if idx >= 0 and idx < len(self.persons):
            self.selected_person_id = self.persons[idx]["id"]
        self.accept()

    @staticmethod
    def _split_name(name: str) -> tuple[str, str]:
        parts = name.split(" ", 1)
        first = parts[0].strip() if parts else ""
        last = parts[1].strip() if len(parts) > 1 else ""
        return first, last
