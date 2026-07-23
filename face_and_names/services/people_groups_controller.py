"""Controller for People & Groups page data access."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from face_and_names.models.repositories import (
    FaceRepository,
    ImageRepository,
    PeopleGroupsRepository,
)


@dataclass(frozen=True)
class PersonFaceRecord:
    """Face row displayed on the People page."""

    face_id: int
    person_id: int | None
    person_name: str | None
    predicted_person_id: int | None
    predicted_name: str | None
    confidence: float | None
    crop: bytes


@dataclass(frozen=True)
class PersonImageRecord:
    """Image row displayed on the People page."""

    image_id: int
    person_id: int | None
    person_name: str | None
    thumb: bytes
    relative_path: str
    predicted_person_id: int | None = None
    predicted_name: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class OriginalFaceImage:
    """Original image path and relative face box for preview."""

    image_path: Path
    bbox_rel: tuple[float, float, float, float]


class PeopleGroupsController:
    """Provide queries and mutations for People & Groups UI."""

    def __init__(self, conn: sqlite3.Connection, db_root: Path) -> None:
        self.conn = conn
        self.db_root = db_root
        self.face_repo = FaceRepository(conn)
        self.image_repo = ImageRepository(conn)
        self.people_repo = PeopleGroupsRepository(conn)

    def delete_face(self, face_id: int) -> None:
        self.face_repo.delete(face_id)
        self.conn.commit()

    def delete_image(self, image_id: int) -> None:
        self.image_repo.delete(image_id)
        self.conn.commit()

    def assign_person(self, face_id: int, person_id: int | None) -> None:
        self.face_repo.update_person(face_id, person_id)
        self.conn.commit()

    def count_faces(
        self, person_id: int, start: datetime | None = None, end: datetime | None = None
    ) -> int:
        return self.people_repo.count_faces(person_id, start, end)

    def count_images(
        self, person_id: int, start: datetime | None = None, end: datetime | None = None
    ) -> int:
        return self.people_repo.count_images(person_id, start, end)

    def fetch_faces(
        self,
        person_id: int,
        limit: int,
        offset: int,
        sort_key: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[PersonFaceRecord]:
        rows = self.people_repo.fetch_faces(person_id, limit, offset, sort_key, start, end)
        return [
            PersonFaceRecord(
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

    def fetch_images(
        self,
        person_id: int,
        limit: int,
        offset: int,
        sort_key: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[PersonImageRecord]:
        rows = self.people_repo.fetch_images(person_id, limit, offset, sort_key, start, end)
        return [
            PersonImageRecord(
                image_id=int(row[0]),
                person_id=row[1],
                person_name=row[2],
                thumb=bytes(row[3]),
                relative_path=row[4],
            )
            for row in rows
        ]

    def original_face_image(self, face_id: int) -> OriginalFaceImage | None:
        row = self.face_repo.get_face_with_image(face_id)
        if row is None:
            return None
        _, _, x, y, w, h, rel_path, _, _ = row
        return OriginalFaceImage(
            image_path=self.db_root / str(rel_path),
            bbox_rel=(float(x), float(y), float(w), float(h)),
        )

    def original_image_path(self, relative_path: str) -> Path:
        return self.db_root / relative_path

    def collect_dates_for_person(self, person_id: int) -> list[datetime]:
        return [
            dt
            for raw in self.people_repo.dates_for_person(person_id)
            if (dt := self.parse_date(raw))
        ]

    def shot_date_for_face(self, face_id: int) -> datetime | None:
        return self.parse_date(self.people_repo.date_for_face(face_id))

    def shot_date_for_image(self, image_id: int) -> datetime | None:
        return self.parse_date(self.people_repo.date_for_image(image_id))

    @staticmethod
    def parse_date(raw: str | None) -> datetime | None:
        if not raw:
            return None
        for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except Exception:
                continue
        try:
            if ":" in raw and raw.count(":") >= 2 and " " in raw:
                parts = raw.split(" ", 1)
                date_part = parts[0].replace(":", "-", 2)
                return datetime.fromisoformat(f"{date_part} {parts[1]}")
        except Exception:
            return None
        return None
