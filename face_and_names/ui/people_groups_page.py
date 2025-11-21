"""
People & Groups management page.

DESIGN:
- UI tech: PyQt6. Display a table of people (id, first, last, short, display) with add/edit/delete.
- Uses PeopleService for CRUD; keeps person_id stable; updates names via rename_person with first/last/short.
- Table double-click opens edit dialog; delete via button; add via button.
- Future: extend with groups; kept minimal for now.
"""

from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from face_and_names.services.people_service import PeopleService


class PeopleTableModel(QAbstractTableModel):
    def __init__(self, people: List[dict]) -> None:
        super().__init__()
        self.people = people
        self.headers = ["ID", "First", "Last", "Short", "Display", "Faces"]

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.people)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = ...) -> object:
        if not index.isValid():
            return None
        row = self.people[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row["id"]
            if col == 1:
                return row["first_name"]
            if col == 2:
                return row["last_name"]
            if col == 3:
                return row["short_name"] or ""
            if col == 4:
                return row["display_name"]
            if col == 5:
                return row.get("face_count", 0)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def update_people(self, people: List[dict]) -> None:
        self.beginResetModel()
        self.people = people
        self.endResetModel()


class PersonEditDialog(QDialog):
    def __init__(self, *, first: str = "", last: str = "", short: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit person")
        self.first_edit = QLineEdit(first)
        self.last_edit = QLineEdit(last)
        self.short_edit = QLineEdit(short)

        form = QVBoxLayout()
        form.addWidget(QLabel("First name"))
        form.addWidget(self.first_edit)
        form.addWidget(QLabel("Last name"))
        form.addWidget(self.last_edit)
        form.addWidget(QLabel("Short name (optional)"))
        form.addWidget(self.short_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def values(self) -> tuple[str, str, str | None]:
        first = self.first_edit.text().strip()
        last = self.last_edit.text().strip()
        short = self.short_edit.text().strip() or None
        return first, last, short


class PeopleGroupsPage(QWidget):
    def __init__(self, people_service: PeopleService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.people_service = people_service
        self.table = QTableView()
        self.model = PeopleTableModel([])
        self.table.setModel(self.model)
        self.table.doubleClicked.connect(self._on_edit)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.add_btn = QPushButton("Add person")
        self.add_btn.clicked.connect(self._on_add)
        self.del_btn = QPushButton("Delete person")
        self.del_btn.clicked.connect(self._on_delete)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(btn_row)
        self.setLayout(layout)

        self._refresh()

    def _refresh(self) -> None:
        people = self.people_service.list_people()
        self.model.update_people(people)

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Refresh people list whenever the page is shown."""
        self._refresh()
        return super().showEvent(event)

    def _selected_person(self) -> dict | None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        return self.model.people[idx.row()]

    def _on_add(self) -> None:
        dlg = PersonEditDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        first, last, short = dlg.values()
        if not first and not last:
            QMessageBox.warning(self, "Missing name", "First or last name is required.")
            return
        pid = self.people_service.create_person(first, last, short_name=short)
        self.people_service.rename_person(pid, first, last, short)
        self._refresh()

    def _on_edit(self) -> None:
        person = self._selected_person()
        if not person:
            return
        dlg = PersonEditDialog(
            first=person.get("first_name", ""),
            last=person.get("last_name", ""),
            short=person.get("short_name") or "",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        first, last, short = dlg.values()
        self.people_service.rename_person(person["id"], first, last, short)
        self._refresh()

    def _on_delete(self) -> None:
        person = self._selected_person()
        if not person:
            return
        confirm = QMessageBox.question(
            self, "Delete person", f"Delete person ID {person['id']} ({person['display_name']})?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.people_service.conn.execute("DELETE FROM person WHERE id = ?", (person["id"],))
        self.people_service.conn.commit()
        self._refresh()
