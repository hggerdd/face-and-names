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
    QLabel,
)
from PyQt6.QtGui import QPixmap

from face_and_names.app_context import (
    AppContext,
    initialize_app,
    load_last_folder,
    load_last_db_path,
    save_last_db_path,
    save_last_folder,
)
from face_and_names.models.db import initialize_database
from face_and_names.services.ingest_service import IngestOptions, IngestService


class IngestWorker(QObject):
    finished = pyqtSignal(object)
    progress = pyqtSignal(object)

    def __init__(self, db_root: Path, folders: Sequence[Path], recursive: bool) -> None:
        super().__init__()
        self.db_root = db_root
        self.folders = folders
        self.recursive = recursive

    def run(self) -> None:
        conn = initialize_database(self.db_root / "faces.db")
        service = IngestService(db_root=self.db_root, conn=conn)
        progress = service.start_session(
            self.folders,
            options=IngestOptions(recursive=self.recursive),
            progress_cb=self.progress.emit,
        )
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
        self.source_list.itemChanged.connect(self._on_item_changed)
        self.recursive_checkbox = QCheckBox("Include subfolders (recursive)")
        self.recursive_checkbox.setChecked(True)
        self.status_label = QLabel("Idle")
        self.folder_label = QLabel("Current folder: -")
        self.image_label = QLabel("Last image: -")
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(160, 160)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ingest_button = QPushButton("Start Ingest")
        self.refresh_button = QPushButton("Refresh folder list")
        self.refresh_button.clicked.connect(self._load_subfolders)

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
        src_row.addWidget(QLabel("Folders under DB Root (check to ingest):"))
        src_row.addWidget(self.refresh_button)
        layout.addLayout(src_row)
        layout.addWidget(self.source_list)

        layout.addWidget(self.recursive_checkbox)

        # Controls
        self.ingest_button.clicked.connect(self._start_ingest)
        layout.addWidget(self.ingest_button)
        layout.addWidget(self.folder_label)
        layout.addWidget(self.image_label)
        layout.addWidget(self.thumb_label)
        layout.addWidget(self.status_label)

        layout.addStretch(1)
        self.setLayout(layout)
        self._load_subfolders()
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
        save_last_db_path(self.config_dir, new_db_path)
        self.db_path_edit.setText(str(self.db_root))
        self.source_list.clear()
        self.on_context_changed(new_context)
        self.status_label.setText("DB Root updated.")
        self._load_subfolders()
        self._prefill_last_folder()

    def _start_ingest(self) -> None:
        folders = self._checked_folders()
        if not folders:
            QMessageBox.warning(self, "No folders", "Select at least one folder to ingest.")
            return
        self.ingest_button.setEnabled(False)
        self.status_label.setText("Ingest running…")
        recursive = self.recursive_checkbox.isChecked()

        self._thread = QThread(self)
        self._worker = IngestWorker(db_root=self.db_root, folders=folders, recursive=recursive)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
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

    def _on_progress(self, progress) -> None:
        self.status_label.setText(
            f"Ingesting… {progress.processed}/{progress.total} processed, skipped {progress.skipped_existing}"
        )
        if progress.current_folder:
            self.folder_label.setText(f"Current folder: {progress.current_folder}")
        if progress.last_image_name:
            self.image_label.setText(f"Last 10th image: {progress.last_image_name}")
        if progress.last_thumbnail:
            pixmap = QPixmap()
            if pixmap.loadFromData(progress.last_thumbnail):
                scaled = pixmap.scaled(
                    self.thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                self.thumb_label.setPixmap(scaled)

    def _prefill_last_folder(self) -> None:
        """Preselect the last used folder if available and in scope."""
        last = load_last_folder(self.config_dir)
        if last and last.exists():
            for i in range(self.source_list.count()):
                item = self.source_list.item(i)
                if Path(item.text()) == last:
                    item.setCheckState(Qt.CheckState.Checked)
                    break

    def _load_subfolders(self) -> None:
        """Populate list with subfolders under DB root."""
        self.source_list.blockSignals(True)
        self.source_list.clear()
        root = self.db_root
        if not root.exists():
            root.mkdir(parents=True, exist_ok=True)
        items = [root]
        items.extend(sorted({p for p in root.rglob("*") if p.is_dir()}))
        for path in items:
            rel = path
            item = QListWidgetItem(str(rel))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.source_list.addItem(item)
        self.source_list.blockSignals(False)

    def _checked_folders(self) -> list[Path]:
        return [
            Path(self.source_list.item(i).text())
            for i in range(self.source_list.count())
            if self.source_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if item.checkState() == Qt.CheckState.Checked:
            save_last_folder(self.config_dir, Path(item.text()))
