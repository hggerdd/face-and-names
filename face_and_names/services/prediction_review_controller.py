"""Controller for advanced prediction review data and actions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from face_and_names.models.repositories import FaceRepository


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

    def predicted_counts(self) -> dict[int, int]:
        """Return pending prediction counts by predicted person."""
        rows = self.conn.execute(
            """
            SELECT predicted_person_id, COUNT(*)
            FROM face
            WHERE predicted_person_id IS NOT NULL
              AND person_id IS NULL
            GROUP BY predicted_person_id
            """
        ).fetchall()
        return {int(row[0]): int(row[1]) for row in rows}

    def count_faces(self, filters: PredictionReviewFilters) -> int:
        """Count faces matching the current filters."""
        where, params = self._filter_clause(filters)
        row = self.conn.execute(f"SELECT COUNT(*) FROM face f WHERE {where}", params).fetchone()
        return int(row[0]) if row else 0

    def load_faces(
        self, filters: PredictionReviewFilters, *, limit: int, offset: int
    ) -> list[PredictionReviewFace]:
        """Load one page of prediction review faces."""
        where, params = self._filter_clause(filters)
        rows = self.conn.execute(
            f"""
            SELECT f.id, f.person_id, p.primary_name, f.predicted_person_id, pp.primary_name,
                   f.prediction_confidence, f.face_crop_blob
            FROM face f
            LEFT JOIN person p ON p.id = f.person_id
            LEFT JOIN person pp ON pp.id = f.predicted_person_id
            WHERE {where}
            ORDER BY COALESCE(f.prediction_confidence, 0) DESC, f.id
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
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
        self.conn.commit()

    def assign_person(self, face_id: int, person_id: int | None) -> None:
        """Assign or clear a person on one face."""
        self.face_repo.update_person(face_id, person_id)
        self.conn.commit()

    def accept_predictions(self, face_ids: list[int]) -> int:
        """Assign predicted persons to selected faces."""
        if not face_ids:
            return 0
        placeholders = ", ".join("?" for _ in face_ids)
        cursor = self.conn.execute(
            f"""
            UPDATE face
            SET person_id = predicted_person_id
            WHERE id IN ({placeholders})
              AND predicted_person_id IS NOT NULL
            """,
            face_ids,
        )
        self.conn.commit()
        return int(cursor.rowcount)

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

    @staticmethod
    def _filter_clause(filters: PredictionReviewFilters) -> tuple[str, list[object]]:
        params: list[object] = []
        clauses = ["f.predicted_person_id IS NOT NULL"]
        if filters.predicted_person_id is not None:
            clauses.append("f.predicted_person_id = ?")
            params.append(filters.predicted_person_id)
        if filters.unnamed_only:
            clauses.append("f.person_id IS NULL")
        clauses.append("COALESCE(f.prediction_confidence, 0) BETWEEN ? AND ?")
        params.extend([filters.confidence_min, filters.confidence_max])
        return " AND ".join(clauses), params
