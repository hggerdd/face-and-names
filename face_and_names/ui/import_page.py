"""
Import view for selecting DB Root and triggering ingestion.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Sequence

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from face_and_names.app_context import (
    AppContext,
    initialize_app,
    load_last_folder,
    save_last_db_path,
    save_last_folder,
)
from face_and_names.models.db import initialize_database
from face_and_names.services.ingest_service import IngestOptions, IngestService


class IngestWorker(QObject):
    finished = pyqtSignal(object)
    progress = pyqtSignal(object)

    def __init__(
        self,
        db_root: Path,
        folders: Sequence[Path],
        recursive: bool,
        cancel_event: threading.Event | None = None,
        checkpoint: dict | None = None,
        crop_expand_pct: float = 0.05,
        face_target_size: int = 224,
        prediction_service=None,
    ) -> None:
        super().__init__()
        self.db_root = db_root
        self.folders = folders
        self.recursive = recursive
        self.cancel_event = cancel_event
        self.checkpoint = checkpoint
        self.crop_expand_pct = crop_expand_pct
        self.face_target_size = face_target_size
        self.prediction_service = prediction_service

    def run(self) -> None:
        conn = initialize_database(self.db_root / "faces.db")
        service = IngestService(
            db_root=self.db_root,
            conn=conn,
            crop_expand_pct=self.crop_expand_pct,
            face_target_size=self.face_target_size,
            prediction_service=self.prediction_service,
        )
        progress = service.start_session(
            self.folders,
            options=IngestOptions(recursive=self.recursive),
            progress_cb=self.progress.emit,
            cancel_event=self.cancel_event,
            checkpoint=self.checkpoint,
        )
        self.finished.emit(progress)


class ImportPage(QWidget):
    """UI for DB Root selection and ingest kickoff."""

    def __init__(
        self, context: AppContext, on_context_changed: Callable[[AppContext], None]
    ) -> None:
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
        self.face_thumb_labels: list[QLabel] = []
        self.ingest_button = QPushButton("Start Ingest")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.refresh_button = QPushButton("Refresh folder list")
        self.refresh_button.clicked.connect(self._load_subfolders)
        self.cancel_event: threading.Event | None = None
        self._last_checkpoint: dict | None = None
        self._last_selected_folders: list[Path] = []

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
        self.cancel_button.clicked.connect(self._cancel_ingest)
        layout.addWidget(self.ingest_button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.folder_label)
        layout.addWidget(self.image_label)
        layout.addWidget(self.thumb_label)
        faces_row = QHBoxLayout()
        faces_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        faces_row.addWidget(QLabel("Faces:"))
        for _ in range(5):
            lbl = QLabel()
            lbl.setFixedSize(64, 64)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.face_thumb_labels.append(lbl)
            faces_row.addWidget(lbl)
        faces_row.addStretch(1)
        layout.addLayout(faces_row)
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
        use_checkpoint = None
        if self._last_checkpoint and folders == self._last_selected_folders:
            use_checkpoint = self._last_checkpoint
        self.ingest_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status_label.setText("Ingest running…")
        recursive = self.recursive_checkbox.isChecked()

        self.cancel_event = threading.Event()
        detector_cfg = (
            self.context.config.get("detector", {}) if isinstance(self.context.config, dict) else {}
        )
        crop_expand_pct = float(detector_cfg.get("crop_expand_pct", 0.05))
        face_target_size = int(detector_cfg.get("face_target_size", 224))
        self._thread = QThread(self)
        self._worker = IngestWorker(
            db_root=self.db_root,
            folders=folders,
            recursive=recursive,
            cancel_event=self.cancel_event,
            checkpoint=use_checkpoint,
            crop_expand_pct=crop_expand_pct,
            face_target_size=face_target_size,
            prediction_service=self.context.prediction_service,
        )
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
        self.cancel_button.setEnabled(False)
        self._last_selected_folders = self._checked_folders()
        if progress.errors:
            self.status_label.setText(
                f"Ingest finished: processed {progress.processed}, skipped {progress.skipped_existing}, "
                f"errors: {len(progress.errors)}"
            )
        else:
            status = (
                "Ingest cancelled" if getattr(progress, "cancelled", False) else "Ingest finished"
            )
            self.status_label.setText(
                f"{status}: processed {progress.processed}, skipped {progress.skipped_existing}"
            )
        if getattr(progress, "cancelled", False):
            self._last_checkpoint = progress.checkpoint
        else:
            self._last_checkpoint = None
        try:
            self.context.events.emit("ingest_completed")
        except Exception:
            pass

    def _on_progress(self, progress) -> None:
        self.status_label.setText(
            f"Ingesting… {progress.processed}/{progress.total} processed, skipped {progress.skipped_existing}, faces {progress.face_count}, no-face {progress.no_face_images}"
        )
        if progress.current_folder:
            self.folder_label.setText(f"Current folder: {progress.current_folder}")
        if progress.last_image_name:
            self.image_label.setText(f"Last 10th image: {progress.last_image_name}")
        if progress.last_thumbnail:
            pixmap = QPixmap()
            if pixmap.loadFromData(progress.last_thumbnail):
                scaled = pixmap.scaled(
                    self.thumb_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.thumb_label.setPixmap(scaled)
        if progress.last_face_thumbs is not None:
            for lbl, data in zip(self.face_thumb_labels, progress.last_face_thumbs):
                px = QPixmap()
                if px.loadFromData(data):
                    lbl.setPixmap(
                        px.scaled(
                            lbl.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
            # clear remaining labels
            if len(progress.last_face_thumbs) < len(self.face_thumb_labels):
                for lbl in self.face_thumb_labels[len(progress.last_face_thumbs) :]:
                    lbl.clear()
        if getattr(progress, "checkpoint", None) is not None:
            self._last_checkpoint = progress.checkpoint

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

    def _cancel_ingest(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.status_label.setText("Cancellation requested…")
