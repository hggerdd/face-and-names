"""Controller for the Faces workspace data and actions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from face_and_names.models.repositories import AuditLogRepository, FaceRepository
from face_and_names.services.people_service import PeopleService

WorkspaceMode = Literal["all", "unnamed", "predicted", "clustered"]


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
    image_id: int | None = None
    filename: str | None = None
    relative_path: str | None = None
    cluster_id: int | None = None


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


@dataclass(frozen=True)
class WorkspaceSummary:
    """Aggregate counts for the current Faces workspace."""

    images: int
    faces: int
    unnamed_faces: int
    predicted_faces: int
    clustered_faces: int


@dataclass(frozen=True)
class FaceWorkspaceFilters:
    """Filters for the unified face grid."""

    folder: str | None = None
    mode: WorkspaceMode = "all"
    confidence_min: float | None = None
    confidence_max: float | None = None
    differs_from_name: bool = False


@dataclass(frozen=True)
class FacePage:
    """One page of face records plus total count."""

    faces: list[FaceTileRecord]
    total: int


class FacesWorkspaceController:
    """Coordinate Faces workspace persistence without leaking SQL into widgets."""

    def __init__(
        self, conn: sqlite3.Connection, db_root: Path, people_service: PeopleService
    ) -> None:
        self.conn = conn
        self.db_root = db_root
        self.people_service = people_service
        self.face_repo = FaceRepository(conn)
        self.audit = AuditLogRepository(conn)

    def list_folders(self) -> list[str]:
        """Return known image folders in display order."""
        return self.face_repo.list_image_folders()

    def load_images(
        self, folder: str, offset: int, limit: int, mode: WorkspaceMode = "all"
    ) -> tuple[list[ImageRecord], int]:
        """Load a page of image records for one folder."""
        rows, total = self.face_repo.load_images(folder, mode, limit=limit, offset=offset)
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

    def workspace_summary(self, folder: str | None = None) -> WorkspaceSummary:
        """Return workspace counts, optionally scoped to a folder."""
        images, face_rows = self.face_repo.workspace_summary(folder)
        return WorkspaceSummary(
            images=images,
            faces=int(face_rows[0] or 0),
            unnamed_faces=int(face_rows[1] or 0),
            predicted_faces=int(face_rows[2] or 0),
            clustered_faces=int(face_rows[3] or 0),
        )

    def load_face_page(self, filters: FaceWorkspaceFilters, offset: int, limit: int) -> FacePage:
        """Load a page of faces for the unified workspace grid."""
        rows, total = self.face_repo.load_face_page(
            folder=filters.folder,
            mode=filters.mode,
            confidence_min=filters.confidence_min,
            confidence_max=filters.confidence_max,
            differs_from_name=filters.differs_from_name,
            offset=offset,
            limit=limit,
        )
        return FacePage(
            faces=[
                FaceTileRecord(
                    face_id=int(row[0]),
                    person_id=row[1],
                    person_name=row[2],
                    predicted_person_id=row[3],
                    predicted_name=row[4],
                    confidence=row[5],
                    crop=bytes(row[6]),
                    image_id=int(row[7]),
                    filename=str(row[8]),
                    relative_path=str(row[9]),
                    cluster_id=row[10],
                )
                for row in rows
            ],
            total=total,
        )

    def accept_predictions(self, face_ids: list[int]) -> int:
        """Assign predicted people to the selected faces where a prediction exists."""
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

    def assign_person_to_faces(self, face_ids: list[int], person_id: int | None) -> int:
        """Assign one person to multiple selected faces."""
        if not face_ids:
            return 0
        cursor = self.face_repo.assign_person_to_faces(face_ids, person_id)
        self.audit.add(
            action="assign_person",
            entity_type="face_batch",
            details=json.dumps({"count": int(cursor), "person_id": person_id}),
        )
        self.conn.commit()
        return int(cursor)

    def load_face_boxes(self, image_id: int) -> list[tuple[float, float, float, float]]:
        """Return relative face boxes for one image."""
        rows = self.face_repo.load_face_boxes(image_id)
        return [(float(row[0]), float(row[1]), float(row[2]), float(row[3])) for row in rows]

    def load_face_tiles(self, image_id: int) -> list[FaceTileRecord]:
        """Return face tile records for one image."""
        rows = self.face_repo.load_face_tiles(image_id)
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
        rows = self.face_repo.load_face_table_rows(image_id)
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
