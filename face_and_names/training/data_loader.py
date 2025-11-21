"""
Training data loader for verified faces stored in SQLite.

Selects only faces with a stable person_id and, when present, a `verified` flag set.
Decodes `face_crop_blob` into RGB PIL images; corrupt rows are skipped with logging.
"""

from __future__ import annotations

import io
import logging
import sqlite3
from dataclasses import dataclass
from typing import Iterable, List

from PIL import Image


logger = logging.getLogger(__name__)


@dataclass
class FaceSample:
    face_id: int
    person_id: int
    image: Image.Image


def _has_verified_column(conn: sqlite3.Connection) -> bool:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(face)").fetchall()}
    return "verified" in cols


def load_verified_faces(conn: sqlite3.Connection, limit: int | None = None) -> List[FaceSample]:
    """
    Return decoded face samples restricted to verified faces.

    Rules:
    - person_id must be present
    - face_crop_blob must be present
    - if a `verified` column exists, it must be true (non-zero)
    """
    conditions = ["person_id IS NOT NULL", "face_crop_blob IS NOT NULL"]
    if _has_verified_column(conn):
        conditions.append("verified = 1")
    where = " AND ".join(conditions)
    sql = f"SELECT id, face_crop_blob, person_id FROM face WHERE {where} ORDER BY person_id, id"
    params: Iterable[int] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)

    rows = conn.execute(sql, params).fetchall()
    samples: list[FaceSample] = []
    for face_id, blob, person_id in rows:
        if blob is None:
            continue
        try:
            img = Image.open(io.BytesIO(blob)).convert("RGB")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Skipping face %s: failed to decode blob (%s)", face_id, exc)
            continue
        samples.append(FaceSample(face_id=int(face_id), person_id=int(person_id), image=img))
    return samples
