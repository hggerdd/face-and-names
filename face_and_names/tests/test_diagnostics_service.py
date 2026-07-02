from __future__ import annotations

from pathlib import Path

from face_and_names.models.db import initialize_database
from face_and_names.services.diagnostics_service import DiagnosticsService


def _write_model_artifacts(model_dir: Path) -> None:
    model_dir.mkdir()
    for filename in (
        "classifier.pkl",
        "person_id_mapping.json",
        "embedding_config.json",
        "metrics.json",
    ):
        (model_dir / filename).write_text("{}", encoding="utf-8")
    (model_dir / "version.txt").write_text("test-version", encoding="utf-8")


def test_diagnostics_service_reports_ok_for_complete_local_setup(tmp_path: Path) -> None:
    db_path = tmp_path / "faces.db"
    conn = initialize_database(db_path)
    registry_path = tmp_path / "persons" / "persons.json"
    registry_path.parent.mkdir()
    registry_path.write_text('{"version": 1, "next_id": 1, "people": []}', encoding="utf-8")
    model_dir = tmp_path / "model"
    _write_model_artifacts(model_dir)
    detector_weights = tmp_path / "yolov11n-face.pt"
    detector_weights.write_bytes(b"weights")

    result = DiagnosticsService(
        conn=conn,
        db_path=db_path,
        registry_path=registry_path,
        model_dir=model_dir,
        detector_weights=detector_weights,
    ).self_test()

    assert result["status"] == "ok"
    checks = result["checks"]
    assert [check.status for check in checks] == ["ok", "ok", "ok", "ok", "ok", "ok"]


def test_diagnostics_service_warns_for_missing_optional_artifacts(tmp_path: Path) -> None:
    db_path = tmp_path / "faces.db"
    conn = initialize_database(db_path)
    registry_path = tmp_path / "persons" / "persons.json"
    registry_path.parent.mkdir()

    result = DiagnosticsService(
        conn=conn,
        db_path=db_path,
        registry_path=registry_path,
        model_dir=tmp_path / "missing-model",
        detector_weights=tmp_path / "missing-detector.pt",
    ).self_test()

    assert result["status"] == "warning"
    checks = {check.name: check for check in result["checks"]}
    assert checks["Person registry"].status == "warning"
    assert checks["Prediction model"].status == "warning"
    assert checks["Detector weights"].status == "warning"
