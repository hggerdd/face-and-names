"""Controller for advanced clustering page UI data and mutations."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from face_and_names.models.repositories import AuditLogRepository, FaceRepository


@dataclass(frozen=True)
class ClusterFaceRecord:
    """Minimal persisted face data needed for cluster rendering."""

    person_id: int | None
    predicted_person_id: int | None


@dataclass(frozen=True)
class OriginalFaceImage:
    """Original image path and relative face box for preview."""

    image_path: Path
    bbox_rel: tuple[float, float, float, float]


class ClusteringPageController:
    """Provide database access for the advanced clustering UI."""

    def __init__(self, conn: sqlite3.Connection, db_root: Path) -> None:
        self.conn = conn
        self.db_root = db_root
        self.face_repo = FaceRepository(conn)
        self.audit = AuditLogRepository(conn)

    def list_folders(self) -> list[str]:
        """Return folders that contain images."""
        return self.face_repo.list_image_subfolders()

    def face_record(self, face_id: int) -> ClusterFaceRecord | None:
        """Return person and prediction IDs for one face."""
        row = self.face_repo.get_face_assignment(face_id)
        if row is None:
            return None
        return ClusterFaceRecord(person_id=row[0], predicted_person_id=row[1])

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

    def assign_person_to_faces(self, face_ids: list[int], person_id: int) -> int:
        """Assign one person to multiple faces."""
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
