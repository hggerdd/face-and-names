"""Controller for People & Groups page data access."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SHOT_DATE_SQL_TEMPLATE = """
    COALESCE(
        (
            SELECT value
            FROM metadata m2
            WHERE m2.image_id = {img_alias}.id
              AND m2.key IN ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime', 'CreateDate')
            ORDER BY CASE m2.key
                WHEN 'DateTimeOriginal' THEN 1
                WHEN 'DateTimeDigitized' THEN 2
                WHEN 'DateTime' THEN 3
                WHEN 'CreateDate' THEN 4
                ELSE 5
            END
            LIMIT 1
        ),
        {session_alias}.import_date
    )
"""


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

    def delete_face(self, face_id: int) -> None:
        self.conn.execute("DELETE FROM face WHERE id = ?", (face_id,))
        self.conn.commit()

    def delete_image(self, image_id: int) -> None:
        self.conn.execute("DELETE FROM image WHERE id = ?", (image_id,))
        self.conn.commit()

    def assign_person(self, face_id: int, person_id: int | None) -> None:
        self.conn.execute("UPDATE face SET person_id = ? WHERE id = ?", (person_id, face_id))
        self.conn.commit()

    def count_faces(
        self, person_id: int, start: datetime | None = None, end: datetime | None = None
    ) -> int:
        params: list[object] = [person_id]
        clause = self._date_filter_clause("i", "s", params, start, end)
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) FROM face f
            JOIN image i ON i.id = f.image_id
            LEFT JOIN import_session s ON s.id = i.import_id
            WHERE f.person_id = ?
            {clause}
            """,
            params,
        ).fetchone()
        return int(row[0]) if row else 0

    def count_images(
        self, person_id: int, start: datetime | None = None, end: datetime | None = None
    ) -> int:
        params: list[object] = [person_id]
        clause = self._date_filter_clause("i", "s", params, start, end)
        row = self.conn.execute(
            f"""
            SELECT COUNT(DISTINCT i.id)
            FROM face f
            JOIN image i ON i.id = f.image_id
            LEFT JOIN import_session s ON s.id = i.import_id
            WHERE f.person_id = ?
            {clause}
            """,
            params,
        ).fetchone()
        return int(row[0]) if row else 0

    def fetch_faces(
        self,
        person_id: int,
        limit: int,
        offset: int,
        sort_key: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[PersonFaceRecord]:
        params: list[object] = [person_id]
        date_clause = self._date_filter_clause("i", "s", params, start, end)
        order_by = self._order_by_sql("i", "s", sort_key)
        rows = self.conn.execute(
            f"""
            SELECT f.id, f.person_id, p.primary_name, f.predicted_person_id, pp.primary_name,
                   f.prediction_confidence, f.face_crop_blob
            FROM face f
            JOIN person p ON p.id = f.person_id
            LEFT JOIN person pp ON pp.id = f.predicted_person_id
            JOIN image i ON i.id = f.image_id
            LEFT JOIN import_session s ON s.id = i.import_id
            WHERE f.person_id = ?
            {date_clause}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
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
        params: list[object] = [person_id]
        date_clause = self._date_filter_clause("i", "s", params, start, end)
        order_by = self._order_by_sql("i", "s", sort_key)
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT i.id, f.person_id, p.primary_name, i.thumbnail_blob, i.relative_path
            FROM face f
            JOIN image i ON i.id = f.image_id
            JOIN person p ON p.id = f.person_id
            LEFT JOIN import_session s ON s.id = i.import_id
            WHERE f.person_id = ?
            {date_clause}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
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
        row = self.conn.execute(
            """
            SELECT f.id, f.image_id, f.bbox_rel_x, f.bbox_rel_y, f.bbox_rel_w, f.bbox_rel_h,
                   i.relative_path, i.width, i.height
            FROM face f
            JOIN image i ON i.id = f.image_id
            WHERE f.id = ?
            """,
            (face_id,),
        ).fetchone()
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
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT i.id, {self._shot_date_expr("i", "s")}
            FROM face f
            JOIN image i ON i.id = f.image_id
            LEFT JOIN import_session s ON s.id = i.import_id
            WHERE f.person_id = ?
            """,
            (person_id,),
        ).fetchall()
        return [dt for _, raw in rows if (dt := self.parse_date(raw))]

    def shot_date_for_face(self, face_id: int) -> datetime | None:
        row = self.conn.execute(
            f"""
            SELECT {self._shot_date_expr("i", "s")}
            FROM face f
            JOIN image i ON i.id = f.image_id
            LEFT JOIN import_session s ON s.id = i.import_id
            WHERE f.id = ?
            """,
            (face_id,),
        ).fetchone()
        return None if row is None else self.parse_date(row[0])

    def shot_date_for_image(self, image_id: int) -> datetime | None:
        row = self.conn.execute(
            """
            SELECT COALESCE((
                SELECT value
                FROM metadata m2
                WHERE m2.image_id = ?
                  AND m2.key IN ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime', 'CreateDate')
                ORDER BY CASE m2.key
                    WHEN 'DateTimeOriginal' THEN 1
                    WHEN 'DateTimeDigitized' THEN 2
                    WHEN 'DateTime' THEN 3
                    WHEN 'CreateDate' THEN 4
                    ELSE 5
                END
                LIMIT 1
            ), import_date)
            FROM import_session
            WHERE id = (SELECT import_id FROM image WHERE id = ?)
            """,
            (image_id, image_id),
        ).fetchone()
        return None if row is None else self.parse_date(row[0])

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

    @staticmethod
    def _shot_date_expr(img_alias: str, session_alias: str) -> str:
        return SHOT_DATE_SQL_TEMPLATE.format(img_alias=img_alias, session_alias=session_alias)

    def _order_by_sql(self, img_alias: str, session_alias: str, sort_key: str) -> str:
        shot = self._shot_date_expr(img_alias, session_alias)
        if sort_key == "date_asc":
            return f"COALESCE({shot}, '') ASC, {img_alias}.id ASC"
        return f"COALESCE({shot}, '') DESC, {img_alias}.id DESC"

    def _date_filter_clause(
        self,
        img_alias: str,
        session_alias: str,
        params: list[object],
        start: datetime | None,
        end: datetime | None,
    ) -> str:
        if start is None or end is None:
            return ""
        shot = self._shot_date_expr(img_alias, session_alias)
        date_expr = f"date(REPLACE(SUBSTR(COALESCE({shot}, '1900-01-01'), 1, 10), ':', '-'))"
        params.extend([start.date().isoformat(), end.date().isoformat()])
        return f"AND {date_expr} BETWEEN ? AND ?"
