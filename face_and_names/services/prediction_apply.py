"""
Reusable helper to apply a trained model to face crops and persist predictions.

This is modular so it can be invoked from UI or from other workflows (e.g., import).
"""

from __future__ import annotations

from typing import Callable
import sqlite3

from face_and_names.models.repositories import FaceRepository
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
    filter_clause = "AND f.person_id IS NULL" if unnamed_only else ""
    rows = conn.execute(
        f"""
        SELECT f.id, f.face_crop_blob, i.relative_path, i.filename
        FROM face f
        JOIN image i ON i.id = f.image_id
        WHERE f.face_crop_blob IS NOT NULL
        {filter_clause}
        ORDER BY f.id
        """
    ).fetchall()
    total = len(rows)
    if total == 0:
        return 0

    repo = FaceRepository(conn)
    count = 0
    for idx, (face_id, blob, rel_path, filename) in enumerate(rows, start=1):
        if should_stop and should_stop():
            break
        label = rel_path or filename or f"face_{face_id}"
        if progress:
            progress(f"Predicting {label}", int(idx / total * 100))
        res = service.predict_batch([blob])[0]
        if assign_person:
            repo.update_person(face_id, res.get("person_id"))
        conn.execute(
            "UPDATE face SET predicted_person_id = ?, prediction_confidence = ? WHERE id = ?",
            (res.get("person_id"), res.get("confidence"), face_id),
        )
        count += 1
    conn.commit()
    return count
