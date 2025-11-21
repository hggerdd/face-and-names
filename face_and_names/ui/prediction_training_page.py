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
)

from face_and_names.app_context import AppContext
from face_and_names.training.trainer import TrainingConfig, train_model_from_db


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


class PredictionTrainingPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.worker: TrainingWorker | None = None

        self.status_label = QLabel("Idle")
        self.summary_label = QLabel("Verified faces: unknown")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.start_btn = QPushButton("Start training")
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)

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

        layout.addStretch(1)
        self.setLayout(layout)

        self.start_btn.clicked.connect(self._start_training)
        self.cancel_btn.clicked.connect(self._cancel_training)

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
