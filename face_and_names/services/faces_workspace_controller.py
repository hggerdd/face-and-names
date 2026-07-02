"""Controller for the Faces workspace data and actions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from face_and_names.models.repositories import FaceRepository
from face_and_names.services.people_service import PeopleService


@dataclass(frozen=True)
class ImageRecord:
    """Image row displayed by the Faces workspace."""

    image_id: int
    filename: str
    relative_path: str
    thumb: bytes
    width: int
    height: int


@dataclass(frozen=True)
class FaceTileRecord:
    """Face data needed to render a reusable face tile."""

    face_id: int
    person_id: int | None
    person_name: str | None
    predicted_person_id: int | None
    predicted_name: str | None
    confidence: float | None
    crop: bytes


@dataclass(frozen=True)
class FaceTableRow:
    """Condensed face row shown in the image details table."""

    person_name: str
    predicted_name: str
    confidence: float | None


@dataclass(frozen=True)
class OriginalFaceImage:
    """Original image path and relative face box for preview."""

    image_path: Path
    bbox_rel: tuple[float, float, float, float]


class FacesWorkspaceController:
    """Coordinate Faces workspace persistence without leaking SQL into widgets."""

    def __init__(
        self, conn: sqlite3.Connection, db_root: Path, people_service: PeopleService
    ) -> None:
        self.conn = conn
        self.db_root = db_root
        self.people_service = people_service
        self.face_repo = FaceRepository(conn)

    def list_folders(self) -> list[str]:
        """Return known image folders in display order."""
        rows = self.conn.execute("SELECT DISTINCT sub_folder FROM image ORDER BY sub_folder")
        return [str(row[0]) for row in rows.fetchall()]

    def load_images(self, folder: str, offset: int, limit: int) -> tuple[list[ImageRecord], int]:
        """Load a page of image records for one folder."""
        total = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM image WHERE sub_folder = ?",
                (folder,),
            ).fetchone()[0]
        )
        rows = self.conn.execute(
            """
            SELECT id, filename, relative_path, thumbnail_blob, width, height
            FROM image
            WHERE sub_folder = ?
            ORDER BY filename
            LIMIT ? OFFSET ?
            """,
            (folder, limit, offset),
        ).fetchall()
        return [
            ImageRecord(
                image_id=int(row[0]),
                filename=str(row[1]),
                relative_path=str(row[2]),
                thumb=bytes(row[3]),
                width=int(row[4]),
                height=int(row[5]),
            )
            for row in rows
        ], total

    def load_face_boxes(self, image_id: int) -> list[tuple[float, float, float, float]]:
        """Return relative face boxes for one image."""
        rows = self.conn.execute(
            """
            SELECT bbox_rel_x, bbox_rel_y, bbox_rel_w, bbox_rel_h
            FROM face
            WHERE image_id = ?
            """,
            (image_id,),
        ).fetchall()
        return [(float(row[0]), float(row[1]), float(row[2]), float(row[3])) for row in rows]

    def load_face_tiles(self, image_id: int) -> list[FaceTileRecord]:
        """Return face tile records for one image."""
        rows = self.conn.execute(
            """
            SELECT f.id, f.person_id, p.primary_name, f.predicted_person_id,
                   pp.primary_name, f.prediction_confidence, f.face_crop_blob
            FROM face f
            LEFT JOIN person p ON p.id = f.person_id
            LEFT JOIN person pp ON pp.id = f.predicted_person_id
            WHERE f.image_id = ?
            ORDER BY f.id
            """,
            (image_id,),
        ).fetchall()
        return [
            FaceTileRecord(
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

    def load_face_table_rows(self, image_id: int) -> list[FaceTableRow]:
        """Return face table rows for one image."""
        rows = self.conn.execute(
            """
            SELECT
                COALESCE(p.primary_name, '') AS person_name,
                COALESCE(pp.primary_name, '') AS predicted_name,
                f.prediction_confidence
            FROM face f
            LEFT JOIN person p ON p.id = f.person_id
            LEFT JOIN person pp ON pp.id = f.predicted_person_id
            WHERE f.image_id = ?
            ORDER BY f.id
            """,
            (image_id,),
        ).fetchall()
        return [
            FaceTableRow(
                person_name=str(row[0]),
                predicted_name=str(row[1]),
                confidence=None if row[2] is None else float(row[2]),
            )
            for row in rows
        ]

    def delete_face(self, face_id: int) -> None:
        """Delete one face and persist the change."""
        self.face_repo.delete(face_id)
        self.conn.commit()

    def assign_person(self, face_id: int, person_id: int | None) -> None:
        """Assign or clear a person on one face."""
        self.face_repo.update_person(face_id, person_id)
        self.conn.commit()

    def create_person(self, first: str, last: str, short_name: str | None = None) -> int:
        """Create a person through the shared people service."""
        return self.people_service.create_person(first, last, short_name=short_name)

    def get_original_face_image(self, face_id: int) -> OriginalFaceImage | None:
        """Return original image preview data for a face."""
        row = self.face_repo.get_face_with_image(face_id)
        if row is None:
            return None
        _, _, x, y, w, h, rel_path, _, _ = row
        return OriginalFaceImage(
            image_path=self.db_root / str(rel_path),
            bbox_rel=(float(x), float(y), float(w), float(h)),
        )
