"""Diagnostics service for local health checks."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from face_and_names.models.db import SCHEMA_VERSION

DiagnosticStatus = Literal["ok", "warning", "error"]

REQUIRED_MODEL_ARTIFACTS = (
    "classifier.pkl",
    "person_id_mapping.json",
    "embedding_config.json",
    "metrics.json",
    "version.txt",
)


@dataclass(frozen=True)
class DiagnosticCheck:
    """One diagnostic result for display and tests."""

    name: str
    status: DiagnosticStatus
    details: str


class DiagnosticsService:
    """Run lightweight local diagnostics without loading heavy ML models."""

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        db_path: Path,
        registry_path: Path,
        model_dir: Path = Path("model"),
        detector_weights: Path = Path("yolov11n-face.pt"),
    ) -> None:
        self.conn = conn
        self.db_path = db_path
        self.registry_path = registry_path
        self.model_dir = model_dir
        self.detector_weights = detector_weights

    def self_test(self) -> dict[str, object]:
        """Return diagnostic checks and a compact overall status."""
        checks = [
            self._check_database(),
            self._check_schema_version(),
            self._check_registry(),
            self._check_model_artifacts(),
            self._check_detector_weights(),
            self._check_data_counts(),
        ]
        return {
            "status": self._overall_status(checks),
            "checks": checks,
        }

    def _check_database(self) -> DiagnosticCheck:
        if not self.db_path.exists():
            return DiagnosticCheck("Database file", "error", f"Missing: {self.db_path}")
        try:
            result = self.conn.execute("PRAGMA quick_check").fetchone()
        except sqlite3.Error as exc:
            return DiagnosticCheck("Database integrity", "error", str(exc))
        value = str(result[0]) if result else "no result"
        status: DiagnosticStatus = "ok" if value.lower() == "ok" else "error"
        return DiagnosticCheck("Database integrity", status, value)

    def _check_schema_version(self) -> DiagnosticCheck:
        try:
            row = self.conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
        except sqlite3.Error as exc:
            return DiagnosticCheck("Schema version", "error", str(exc))
        if row is None:
            return DiagnosticCheck("Schema version", "error", "Missing schema_version row")
        version = int(row[0])
        if version == SCHEMA_VERSION:
            return DiagnosticCheck("Schema version", "ok", f"{version}")
        if version < SCHEMA_VERSION:
            return DiagnosticCheck(
                "Schema version", "warning", f"{version}, expected {SCHEMA_VERSION}"
            )
        return DiagnosticCheck("Schema version", "error", f"{version}, newer than supported")

    def _check_registry(self) -> DiagnosticCheck:
        if self.registry_path.exists():
            return DiagnosticCheck("Person registry", "ok", str(self.registry_path))
        if self.registry_path.parent.exists():
            return DiagnosticCheck(
                "Person registry",
                "warning",
                f"Missing registry file; it will be created at {self.registry_path}",
            )
        return DiagnosticCheck(
            "Person registry", "error", f"Missing registry folder: {self.registry_path.parent}"
        )

    def _check_model_artifacts(self) -> DiagnosticCheck:
        missing = [
            name for name in REQUIRED_MODEL_ARTIFACTS if not (self.model_dir / name).exists()
        ]
        if missing:
            return DiagnosticCheck(
                "Prediction model",
                "warning",
                f"Missing artifacts in {self.model_dir}: {', '.join(missing)}",
            )
        version = (self.model_dir / "version.txt").read_text(encoding="utf-8").strip()
        return DiagnosticCheck("Prediction model", "ok", f"Artifacts present, version {version}")

    def _check_detector_weights(self) -> DiagnosticCheck:
        if self.detector_weights.exists():
            return DiagnosticCheck("Detector weights", "ok", str(self.detector_weights))
        return DiagnosticCheck("Detector weights", "warning", f"Missing: {self.detector_weights}")

    def _check_data_counts(self) -> DiagnosticCheck:
        try:
            image_count = int(self.conn.execute("SELECT COUNT(*) FROM image").fetchone()[0])
            face_count = int(self.conn.execute("SELECT COUNT(*) FROM face").fetchone()[0])
            person_count = int(self.conn.execute("SELECT COUNT(*) FROM person").fetchone()[0])
        except sqlite3.Error as exc:
            return DiagnosticCheck("Data counts", "error", str(exc))
        return DiagnosticCheck(
            "Data counts",
            "ok",
            f"{image_count} images, {face_count} faces, {person_count} people",
        )

    @staticmethod
    def _overall_status(checks: list[DiagnosticCheck]) -> DiagnosticStatus:
        statuses = {check.status for check in checks}
        if "error" in statuses:
            return "error"
        if "warning" in statuses:
            return "warning"
        return "ok"
