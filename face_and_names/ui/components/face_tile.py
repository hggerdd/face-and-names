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
        img_layout = QVBoxLayout()
        img_layout.setContentsMargins(4, 4, 4, 4)
        img_layout.setSpacing(0)

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
        self.image_label.setMinimumSize(120, 120)
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
                140, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
            self.image_label.setGraphicsEffect(None)
        else:
            img: QImage = self._orig_pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
            pix = QPixmap.fromImage(img).scaled(
                140, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
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
        menu = QMenu(self)
        persons = list(self.list_persons_cb())
        for person in persons:
            act = QAction(person["primary_name"], self)
            act.triggered.connect(lambda _, pid=person["id"]: self._assign_person(pid))
            menu.addAction(act)
        if persons:
            menu.addSeparator()
        add_act = QAction("Add new person...", self)
        add_act.triggered.connect(self._add_person)
        menu.addAction(add_act)
        if self.data.person_id is not None:
            rename_act = QAction("Rename assigned person...", self)
            rename_act.triggered.connect(self._rename_person)
            menu.addAction(rename_act)
        menu.exec(self.mapToGlobal(self.assigned_label.pos()))

    def _assign_person(self, person_id: int) -> None:
        if not self.data:
            return
        try:
            self.assign_person_cb(self.data.face_id, person_id)
            self.personAssigned.emit(self.data.face_id, person_id)
            # refresh label to selected name
            for person in self.list_persons_cb():
                if person["id"] == person_id:
                    self.assigned_label.setText(person["primary_name"])
                    self.data.person_id = person_id
                    self.data.person_name = person["primary_name"]
                    break
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "Assign failed", str(exc))

    def _add_person(self) -> None:
        if not self.data:
            return
        name, ok = QInputDialog.getText(self, "New person", "Name:")
        if not ok or not name.strip():
            return
        try:
            pid = self.create_person_cb(name.strip())
            self.personCreated.emit(pid, name.strip())
            self._assign_person(pid)
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "Create failed", str(exc))

    def _rename_person(self) -> None:
        if not self.data or self.data.person_id is None:
            return
        current = self.data.person_name or ""
        new_name, ok = QInputDialog.getText(self, "Rename person", "New name:", text=current)
        if not ok or not new_name.strip():
            return
        try:
            self.rename_person_cb(self.data.person_id, new_name.strip())
            self.personRenamed.emit(self.data.person_id, new_name.strip())
            self.assigned_label.setText(new_name.strip())
            self.data.person_name = new_name.strip()
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "Rename failed", str(exc))

    def _open_original(self) -> None:
        if not self.data:
            return
        if self.open_original_cb:
            self.open_original_cb(self.data.face_id)
        else:
            self.openOriginalRequested.emit(self.data.face_id)
