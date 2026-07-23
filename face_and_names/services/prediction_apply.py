"""
Reusable helper to apply a trained model to face crops and persist predictions.

This is modular so it can be invoked from UI or from other workflows (e.g., import).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Callable

from face_and_names.models.repositories import AuditLogRepository, FaceRepository
from face_and_names.services.prediction_service import PredictionService


def apply_predictions(
    conn: sqlite3.Connection,
    service: PredictionService,
    *,
    unnamed_only: bool = False,
    assign_person: bool = False,
    progress: Callable[[str, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> int:
    """
    Apply predictions to faces in the database.

    Args:
        conn: open sqlite3 connection.
        service: initialized PredictionService (already loaded model).
        unnamed_only: if True, only faces without a person_id are processed.
        progress: optional callback(label, percent).
        should_stop: optional cancellation callback.

    Returns:
        count of faces processed.
    """
    repo = FaceRepository(conn)
    rows = repo.list_prediction_candidates(unnamed_only=unnamed_only)
    total = len(rows)
    if total == 0:
        return 0

    audit = AuditLogRepository(conn)
    service.bind_connection(conn)
    count = 0
    for idx, (face_id, blob, rel_path, filename) in enumerate(rows, start=1):
        if should_stop and should_stop():
            break
        label = rel_path or filename or f"face_{face_id}"
        if progress:
            progress(f"Predicting {label}", int(idx / total * 100))
        res = service.predict_batch([blob], face_ids=[int(face_id)])[0]
        repo.update_prediction(
            int(face_id),
            res.get("person_id"),
            res.get("confidence"),
            assign_person=assign_person,
        )
        audit.add(
            action="apply_prediction",
            entity_type="face",
            entity_id=int(face_id),
            details=json.dumps(
                {
                    "predicted_person_id": res.get("person_id"),
                    "assigned": assign_person,
                }
            ),
        )
        count += 1
    conn.commit()
    return count
