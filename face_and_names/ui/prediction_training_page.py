"""
Prediction model training UI.

Allows starting, monitoring, and cancelling training using the headless pipeline.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QHBoxLayout,
    QWidget,
    QMessageBox,
    QCheckBox,
)

from face_and_names.app_context import AppContext
from face_and_names.training.trainer import TrainingConfig, train_model_from_db
from face_and_names.services.prediction_service import PredictionService
from face_and_names.models.repositories import FaceRepository
from face_and_names.models.db import connect


class TrainingWorker(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, context: AppContext, model_dir: Path):
        super().__init__()
        self.context = context
        self.model_dir = model_dir
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            cfg = TrainingConfig(model_dir=self.model_dir)

            def report(stage: str, current: int, total: int) -> None:
                pct = 0 if total == 0 else int((current / max(total, 1)) * 100)
                self.progress.emit(stage, pct)

            metrics = train_model_from_db(
                self.context.db_path,
                config=cfg,
                progress=report,
                should_stop=lambda: self._stop.is_set(),
            )
            self.finished.emit(metrics)
        except Exception as exc:  # pragma: no cover - UI safety
            self.failed.emit(str(exc))


class PredictionApplyWorker(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, context: AppContext, service: PredictionService, unnamed_only: bool = False):
        super().__init__()
        self.context = context
        self.service = service
        self.unnamed_only = unnamed_only
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            count = apply_predictions(
                self.context.conn,
                self.service,
                unnamed_only=self.unnamed_only,
                progress=lambda label, pct: self.progress.emit(label, pct),
                should_stop=lambda: self._stop.is_set(),
            )
            self.finished.emit(count)
        except Exception as exc:  # pragma: no cover - UI safety
            self.failed.emit(str(exc))


class PredictionTrainingPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.worker: TrainingWorker | None = None
        self.predict_worker: PredictionApplyWorker | None = None

        self.status_label = QLabel("Idle")
        self.summary_label = QLabel("Verified faces: unknown")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.start_btn = QPushButton("Start training")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.apply_btn = QPushButton("Apply model")
        self.apply_cancel_btn = QPushButton("Cancel apply")
        self.apply_cancel_btn.setEnabled(False)
        self.unnamed_only = QCheckBox("Only unnamed faces")
        self.apply_status = QLabel("Prediction idle")
        self.apply_progress = QProgressBar()
        self.apply_progress.setRange(0, 100)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>Prediction model training</b>"), alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        row = QHBoxLayout()
        row.addWidget(self.start_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(QLabel("<b>Apply model to faces</b>"), alignment=Qt.AlignmentFlag.AlignTop)
        apply_row = QHBoxLayout()
        apply_row.addWidget(self.apply_btn)
        apply_row.addWidget(self.apply_cancel_btn)
        apply_row.addWidget(self.unnamed_only)
        apply_row.addStretch(1)
        layout.addLayout(apply_row)
        layout.addWidget(self.apply_status)
        layout.addWidget(self.apply_progress)

        layout.addStretch(1)
        self.setLayout(layout)

        self.start_btn.clicked.connect(self._start_training)
        self.cancel_btn.clicked.connect(self._cancel_training)
        self.apply_btn.clicked.connect(self._start_apply)
        self.apply_cancel_btn.clicked.connect(self._cancel_apply)

    def _start_training(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        model_dir = Path("model")
        self.worker = TrainingWorker(self.context, model_dir)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting...")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.worker.start()

    def _cancel_training(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.status_label.setText("Cancelling...")
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, stage: str, percent: int) -> None:
        self.status_label.setText(f"{stage}...")
        self.progress_bar.setValue(percent)

    def _on_finished(self, metrics: dict) -> None:
        self.status_label.setText(f"Done. Classes={metrics.get('classes')} Samples={metrics.get('samples')}")
        self.progress_bar.setValue(100)
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

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
        self.apply_status.setText("Starting apply...")
        self.apply_btn.setEnabled(False)
        self.apply_cancel_btn.setEnabled(True)
        self.predict_worker.start()

    def _cancel_apply(self) -> None:
        if self.predict_worker and self.predict_worker.isRunning():
            self.predict_worker.stop()
            self.apply_status.setText("Cancelling...")
            self.apply_cancel_btn.setEnabled(False)

    def _on_apply_progress(self, label: str, pct: int) -> None:
        self.apply_status.setText(label)
        self.apply_progress.setValue(pct)

    def _on_apply_finished(self, count: int) -> None:
        self.apply_status.setText(f"Applied to {count} faces")
        self.apply_progress.setValue(100)
        self.apply_btn.setEnabled(True)
        self.apply_cancel_btn.setEnabled(False)

    def _on_apply_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Prediction apply failed", message)
        self.apply_status.setText("Failed")
        self.apply_btn.setEnabled(True)
        self.apply_cancel_btn.setEnabled(False)
from face_and_names.services.prediction_apply import apply_predictions
