"""
Prediction model training UI.

Allows starting, monitoring, and cancelling training using the headless pipeline.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from face_and_names.app_context import AppContext
from face_and_names.services.people_service import PeopleService
from face_and_names.ui.workers import PredictionApplyWorker, TrainingWorker


class PredictionTrainingPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.worker: TrainingWorker | None = None
        self.predict_worker: PredictionApplyWorker | None = None

        self.status_label = QLabel("Training idle.")
        self.summary_label = QLabel("Verified faces: unknown")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.start_btn = QPushButton("Train prediction model")
        self.cancel_btn = QPushButton("Stop training")
        self.cancel_btn.setEnabled(False)
        self.apply_btn = QPushButton("Run predictions")
        self.apply_cancel_btn = QPushButton("Stop predictions")
        self.apply_cancel_btn.setEnabled(False)
        self.unnamed_only = QCheckBox("Only faces without assigned person")
        self.apply_status = QLabel("Prediction idle.")
        self.apply_progress = QProgressBar()
        self.apply_progress.setRange(0, 100)
        self.cm_label = QLabel("Confusion matrix (eligible IDs >50 imgs):")
        self.cm_table = QTableWidget(0, 0)
        self.cm_table.setVisible(False)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(
            QLabel("<h2>Prediction Model Training</h2>"), alignment=Qt.AlignmentFlag.AlignTop
        )
        intro = QLabel(
            "Train model artifacts from verified named faces, then write predictions back for review in Faces."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        row = QHBoxLayout()
        row.addWidget(self.start_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(
            QLabel("<b>Run predictions on faces</b>"), alignment=Qt.AlignmentFlag.AlignTop
        )
        apply_row = QHBoxLayout()
        apply_row.addWidget(self.apply_btn)
        apply_row.addWidget(self.apply_cancel_btn)
        apply_row.addWidget(self.unnamed_only)
        apply_row.addStretch(1)
        layout.addLayout(apply_row)
        layout.addWidget(self.apply_status)
        layout.addWidget(self.apply_progress)
        layout.addWidget(self.cm_label)
        layout.addWidget(self.cm_table)

        layout.addStretch(1)
        self.setLayout(layout)

        self.start_btn.clicked.connect(self._start_training)
        self.cancel_btn.clicked.connect(self._cancel_training)
        self.apply_btn.clicked.connect(self._start_apply)
        self.apply_cancel_btn.clicked.connect(self._cancel_apply)
        self._render_confusion({})

    def _start_training(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        model_dir = Path("model")
        self.worker = TrainingWorker(self.context, model_dir)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting training...")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.worker.start()

    def _cancel_training(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.status_label.setText("Stopping training...")
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, stage: str, percent: int) -> None:
        self.status_label.setText(f"{stage}...")
        self.progress_bar.setValue(percent)

    def _on_finished(self, metrics: dict) -> None:
        self.status_label.setText(
            f"Done. Classes={metrics.get('classes')} Samples={metrics.get('samples')}"
        )
        self.progress_bar.setValue(100)
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._render_confusion(metrics)

    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Training failed", message)
        self.status_label.setText("Failed")
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    # --- Apply model to faces ---
    def _start_apply(self) -> None:
        if self.predict_worker and self.predict_worker.isRunning():
            return
        try:
            from face_and_names.services.prediction_service import PredictionService

            service = PredictionService(model_dir=Path("model"))
        except Exception as exc:  # pragma: no cover - UI safety
            QMessageBox.critical(self, "Model load failed", str(exc))
            return
        self.predict_worker = PredictionApplyWorker(
            context=self.context,
            service=service,
            unnamed_only=self.unnamed_only.isChecked(),
        )
        self.predict_worker.progress.connect(self._on_apply_progress)
        self.predict_worker.finished.connect(self._on_apply_finished)
        self.predict_worker.failed.connect(self._on_apply_failed)
        self.apply_progress.setValue(0)
        self.apply_status.setText("Starting predictions...")
        self.apply_btn.setEnabled(False)
        self.apply_cancel_btn.setEnabled(True)
        self.predict_worker.start()

    def _cancel_apply(self) -> None:
        if self.predict_worker and self.predict_worker.isRunning():
            self.predict_worker.stop()
            self.apply_status.setText("Stopping predictions...")
            self.apply_cancel_btn.setEnabled(False)

    def _on_apply_progress(self, label: str, pct: int) -> None:
        self.apply_status.setText(label)
        self.apply_progress.setValue(pct)

    def _on_apply_finished(self, count: int) -> None:
        self.apply_status.setText(f"Predictions written for {count} faces")
        self.apply_progress.setValue(100)
        self.apply_btn.setEnabled(True)
        self.apply_cancel_btn.setEnabled(False)

    def _on_apply_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Prediction apply failed", message)
        self.apply_status.setText("Failed")
        self.apply_btn.setEnabled(True)
        self.apply_cancel_btn.setEnabled(False)
        self._render_confusion({})

    def _render_confusion(self, metrics: dict) -> None:
        cm = metrics.get("confusion_matrix") if isinstance(metrics, dict) else None
        labels = metrics.get("confusion_labels") if isinstance(metrics, dict) else None
        if not cm or not labels:
            self.cm_table.setVisible(False)
            return
        # Map person_id to display name
        name_map = {}
        try:
            service = getattr(self.context, "people_service", None) or PeopleService(
                self.context.conn, registry_path=getattr(self.context, "registry_path", None)
            )
            for p in service.list_people():
                name_map[p["id"]] = p.get("display_name") or p.get("primary_name")
        except Exception:
            pass
        horiz = [f"{pid} ({name_map.get(pid, '')})" for pid in labels]
        vert = horiz
        self.cm_table.setRowCount(len(labels))
        self.cm_table.setColumnCount(len(labels))
        self.cm_table.setHorizontalHeaderLabels(horiz)
        self.cm_table.setVerticalHeaderLabels(vert)
        for r_idx, row in enumerate(cm):
            for c_idx, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.cm_table.setItem(r_idx, c_idx, item)
        # Apply color scale (white to dark blue)
        flat = [v for row in cm for v in row]
        vmax = max(flat) if flat else 0
        vmin = min(flat) if flat else 0
        span = max(vmax - vmin, 1)
        for r_idx, row in enumerate(cm):
            for c_idx, val in enumerate(row):
                norm = (val - vmin) / span
                # simple blue ramp: white -> dark blue
                b = int(255 * (0.3 + 0.7 * norm))
                g = int(255 * (0.3 + 0.7 * norm))
                r = 255 - int(200 * norm)
                color = QColor(r, g, b)
                self.cm_table.item(r_idx, c_idx).setBackground(color)
        self.cm_table.resizeColumnsToContents()
        self.cm_table.setVisible(True)
