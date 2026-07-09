"""Qt worker classes for long-running UI-triggered jobs."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Sequence

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from face_and_names.app_context import AppContext
from face_and_names.models.db import connect, initialize_database
from face_and_names.services.clustering_service import ClusteringOptions, ClusteringService
from face_and_names.services.ingest_service import IngestOptions, IngestService
from face_and_names.services.prediction_apply import apply_predictions
from face_and_names.services.prediction_service import PredictionService
from face_and_names.training.trainer import TrainingConfig, train_model_from_db


class IngestWorker(QObject):
    """Run photo ingest on a dedicated Qt thread."""

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
        detector_weights: Path | None = None,
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
        self.detector_weights = detector_weights

    def run(self) -> None:
        conn = initialize_database(self.db_root / "faces.db")
        try:
            service = IngestService(
                db_root=self.db_root,
                conn=conn,
                crop_expand_pct=self.crop_expand_pct,
                face_target_size=self.face_target_size,
                prediction_service=self.prediction_service,
                detector_weights=self.detector_weights,
            )
            progress = service.start_session(
                self.folders,
                options=IngestOptions(recursive=self.recursive),
                progress_cb=self.progress.emit,
                cancel_event=self.cancel_event,
                checkpoint=self.checkpoint,
            )
        finally:
            conn.close()
        self.finished.emit(progress)


class TrainingWorker(QThread):
    """Train prediction model artifacts without blocking the UI."""

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
    """Apply an existing prediction model to faces without blocking the UI."""

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
            conn = connect(self.context.db_path)
            try:
                count = apply_predictions(
                    conn,
                    self.service,
                    unnamed_only=self.unnamed_only,
                    assign_person=False,
                    progress=lambda label, pct: self.progress.emit(label, pct),
                    should_stop=lambda: self._stop.is_set(),
                )
                self.finished.emit(count)
            finally:
                conn.close()
        except Exception as exc:  # pragma: no cover - UI safety
            self.failed.emit(str(exc))


class ClusteringWorker(QObject):
    """Run clustering on a dedicated Qt thread."""

    finished = pyqtSignal(object, object)

    def __init__(
        self,
        db_path: Path,
        folders: Sequence[str],
        last_import_only: bool,
        exclude_named: bool,
        algorithm: str,
        eps: float,
        min_samples: int,
        k_clusters: int,
        feature_source: str,
    ) -> None:
        super().__init__()
        self.db_path = db_path
        self.folders = folders
        self.last_import_only = last_import_only
        self.exclude_named = exclude_named
        self.algorithm = algorithm
        self.eps = eps
        self.min_samples = min_samples
        self.k_clusters = k_clusters
        self.feature_source = feature_source

    def run(self) -> None:
        try:
            conn = connect(self.db_path)
            try:
                service = ClusteringService(conn)
                options = ClusteringOptions(
                    last_import_only=self.last_import_only,
                    exclude_named=self.exclude_named,
                    folders=self.folders,
                    eps=self.eps,
                    min_samples=self.min_samples,
                    k_clusters=self.k_clusters,
                    algorithm=self.algorithm,
                    feature_source=self.feature_source,
                )
                result = service.cluster_faces(options)
            finally:
                conn.close()
            self.finished.emit(result, None)
        except Exception as exc:  # pragma: no cover - UI safety
            self.finished.emit([], exc)
