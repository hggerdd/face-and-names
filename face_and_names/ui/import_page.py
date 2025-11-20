"""
Import view for selecting DB Root and triggering ingestion.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Sequence

from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QFileDialog,
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLineEdit,
    QMessageBox,
)

from face_and_names.app_context import AppContext, initialize_app, load_last_folder, save_last_folder
from face_and_names.models.db import initialize_database
from face_and_names.services.ingest_service import IngestOptions, IngestService


class IngestWorker(QObject):
    finished = pyqtSignal(object)

    def __init__(self, db_root: Path, folders: Sequence[Path], recursive: bool) -> None:
        super().__init__()
        self.db_root = db_root
        self.folders = folders
        self.recursive = recursive

    def run(self) -> None:
        conn = initialize_database(self.db_root / "faces.db")
        service = IngestService(db_root=self.db_root, conn=conn)
        progress = service.start_session(self.folders, options=IngestOptions(recursive=self.recursive))
        self.finished.emit(progress)


class ImportPage(QWidget):
    """UI for DB Root selection and ingest kickoff."""

    def __init__(self, context: AppContext, on_context_changed: Callable[[AppContext], None]) -> None:
        super().__init__()
        self.context = context
        self.on_context_changed = on_context_changed
        self.db_root = context.db_path.parent
        self.config_dir = context.config_path.parent

        self.db_path_edit = QLineEdit(str(self.db_root))
        self.db_path_edit.setReadOnly(True)
        self.source_list = QListWidget()
        self.recursive_checkbox = QCheckBox("Include subfolders (recursive)")
        self.recursive_checkbox.setChecked(True)
        self.status_label = QLabel("Idle")
        self.ingest_button = QPushButton("Start Ingest")

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # DB root selector
        db_row = QHBoxLayout()
        db_row.addWidget(QLabel("DB Root (SQLite folder):"))
        db_row.addWidget(self.db_path_edit, stretch=1)
        choose_db = QPushButton("Choose…")
        choose_db.clicked.connect(self._choose_db_root)
        db_row.addWidget(choose_db)
        layout.addLayout(db_row)

        # Source folders list
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Source folders under DB Root:"))
        add_folder = QPushButton("Add folder…")
        add_folder.clicked.connect(self._add_folder)
        src_row.addWidget(add_folder)
        layout.addLayout(src_row)
        layout.addWidget(self.source_list)

        layout.addWidget(self.recursive_checkbox)

        # Controls
        self.ingest_button.clicked.connect(self._start_ingest)
        layout.addWidget(self.ingest_button)
        layout.addWidget(self.status_label)

        layout.addStretch(1)
        self.setLayout(layout)
        self._prefill_last_folder()

    def _choose_db_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select DB Root")
        if not chosen:
            return
        new_root = Path(chosen)
        new_db_path = new_root / "faces.db"
        # Reinitialize context with new DB path
        new_context = initialize_app(db_path=new_db_path)
        self.context.conn.close()
        self.context = new_context
        self.db_root = new_root
        self.config_dir = new_context.config_path.parent
        self.db_path_edit.setText(str(self.db_root))
        self.source_list.clear()
        self.on_context_changed(new_context)
        self.status_label.setText("DB Root updated.")
        self._prefill_last_folder()

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add Folder Under DB Root", str(self.db_root))
        if not folder:
            return
        folder_path = Path(folder)
        try:
            folder_path.resolve().relative_to(self.db_root.resolve())
        except Exception:
            QMessageBox.warning(self, "Out of scope", "Folder must be inside the DB Root.")
            return
        item = QListWidgetItem(str(folder_path))
        self.source_list.addItem(item)
        save_last_folder(self.config_dir, folder_path)

    def _start_ingest(self) -> None:
        folders = [Path(self.source_list.item(i).text()) for i in range(self.source_list.count())]
        if not folders:
            QMessageBox.warning(self, "No folders", "Add at least one folder to ingest.")
            return
        self.ingest_button.setEnabled(False)
        self.status_label.setText("Ingest running…")
        recursive = self.recursive_checkbox.isChecked()

        self._thread = QThread(self)
        self._worker = IngestWorker(db_root=self.db_root, folders=folders, recursive=recursive)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_ingest_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_ingest_finished(self, progress) -> None:
        self.ingest_button.setEnabled(True)
        if progress.errors:
            self.status_label.setText(
                f"Ingest finished: processed {progress.processed}, skipped {progress.skipped_existing}, "
                f"errors: {len(progress.errors)}"
            )
        else:
            self.status_label.setText(
                f"Ingest finished: processed {progress.processed}, skipped {progress.skipped_existing}"
            )

    def _prefill_last_folder(self) -> None:
        """Preselect the last used folder if available and in scope."""
        last = load_last_folder(self.config_dir)
        if last and last.exists():
            try:
                last.resolve().relative_to(self.db_root.resolve())
            except Exception:
                return
            self.source_list.clear()
            self.source_list.addItem(QListWidgetItem(str(last)))
