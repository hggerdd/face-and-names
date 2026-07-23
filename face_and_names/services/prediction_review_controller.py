"""Controller for advanced prediction review data and actions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from face_and_names.models.repositories import AuditLogRepository, FaceRepository


@dataclass(frozen=True)
class PredictionReviewFilters:
    """Filters for advanced prediction review."""

    predicted_person_id: int | None
    confidence_min: float
    confidence_max: float
    unnamed_only: bool


@dataclass(frozen=True)
class PredictionReviewFace:
    """Face row rendered by the advanced prediction review grid."""

    face_id: int
    person_id: int | None
    predicted_person_id: int | None
    person_name: str | None
    predicted_name: str | None
    confidence: float | None
    crop: bytes


@dataclass(frozen=True)
class OriginalFaceImage:
    """Original image path and relative face box for preview."""

    image_path: Path
    bbox_rel: tuple[float, float, float, float]


class PredictionReviewController:
    """Provide prediction review queries and mutations for the UI."""

    def __init__(self, conn: sqlite3.Connection, db_root: Path) -> None:
        self.conn = conn
        self.db_root = db_root
        self.face_repo = FaceRepository(conn)
        self.audit = AuditLogRepository(conn)

    def predicted_counts(self) -> dict[int, int]:
        """Return pending prediction counts by predicted person."""
        rows = self.face_repo.prediction_counts()
        return {int(row[0]): int(row[1]) for row in rows}

    def count_faces(self, filters: PredictionReviewFilters) -> int:
        """Count faces matching the current filters."""
        return self.face_repo.count_prediction_faces(
            filters.predicted_person_id,
            filters.confidence_min,
            filters.confidence_max,
            filters.unnamed_only,
        )

    def load_faces(
        self, filters: PredictionReviewFilters, *, limit: int, offset: int
    ) -> list[PredictionReviewFace]:
        """Load one page of prediction review faces."""
        rows = self.face_repo.load_prediction_faces(
            filters.predicted_person_id,
            filters.confidence_min,
            filters.confidence_max,
            filters.unnamed_only,
            limit=limit,
            offset=offset,
        )
        return [
            PredictionReviewFace(
                face_id=int(row[0]),
                person_id=row[1],
                person_name=row[2],
                predicted_person_id=row[3],
                predicted_name=row[4],
                confidence=row[5],
                crop=bytes(row[6]),
            )
            for row in rows
        ]

    def delete_face(self, face_id: int) -> None:
        """Delete one face."""
        self.face_repo.delete(face_id)
        self.audit.add(
            action="delete",
            entity_type="face",
            entity_id=face_id,
            details=json.dumps({"face_id": face_id}),
        )
        self.conn.commit()

    def assign_person(self, face_id: int, person_id: int | None) -> None:
        """Assign or clear a person on one face."""
        self.face_repo.update_person(face_id, person_id)
        self.audit.add(
            action="assign_person",
            entity_type="face",
            entity_id=face_id,
            details=json.dumps({"face_id": face_id, "person_id": person_id}),
        )
        self.conn.commit()

    def accept_predictions(self, face_ids: list[int]) -> int:
        """Assign predicted persons to selected faces."""
        if not face_ids:
            return 0
        cursor = self.face_repo.accept_predictions(face_ids)
        self.audit.add(
            action="accept_predictions",
            entity_type="face_batch",
            details=json.dumps({"count": int(cursor)}),
        )
        self.conn.commit()
        return int(cursor)

    def get_original_face_image(self, face_id: int) -> OriginalFaceImage | None:
        """Return original image path and face box for preview."""
        row = self.face_repo.get_face_with_image(face_id)
        if row is None:
            return None
        _, _, x, y, w, h, rel_path, _, _ = row
        return OriginalFaceImage(
            image_path=self.db_root / str(rel_path),
            bbox_rel=(float(x), float(y), float(w), float(h)),
        )
