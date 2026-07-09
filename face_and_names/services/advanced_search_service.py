from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, List

from face_and_names.services.people_service import PeopleService

LOGGER = logging.getLogger(__name__)


class LogicOperator(str, Enum):
    AND = "AND"
    OR = "OR"


class FilterType(str, Enum):
    NAME_FUZZY = "NAME_FUZZY"
    DATE_RANGE = "DATE_RANGE"
    PERSON_COUNT = "PERSON_COUNT"


@dataclass
class SearchCriterion:
    filter_type: FilterType
    operator: LogicOperator  # Operator connecting to the PREVIOUS criterion (ignored for first)
    value: Any  # Dict or primitive depending on type


@dataclass
class ImageSearchResult:
    image_id: int
    relative_path: str
    thumbnail_blob: bytes
    match_reason: str


def fuzzy_match(s1: str, s2: str) -> float:
    """
    Return a similarity score between 0.0 and 1.0.
    s1: Database value (can be None)
    s2: User query
    """
    if not s1 or not s2:
        return 0.0
    # Quick check for exact substring
    if s2.lower() in s1.lower():
        return 1.0
    return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


class AdvancedSearchService:
    def __init__(self, people_service: PeopleService):
        self.people_service = people_service
        self.conn = people_service.conn
        db_path = self.conn.execute("PRAGMA database_list").fetchone()[2]
        self.db_root = Path(db_path).parent
        self._register_functions()

    def _register_functions(self):
        try:
            self.conn.create_function("fuzzy_match", 2, fuzzy_match)
        except Exception as e:
            LOGGER.warning(f"Could not register fuzzy_match function: {e}")

    def search(self, criteria: List[SearchCriterion]) -> List[ImageSearchResult]:
        if not criteria:
            return []

        # Base query
        # We need DISTINCT because multiple faces might match the same image
        sql = """
            SELECT DISTINCT i.id, i.relative_path, i.thumbnail_blob
            FROM image i
            LEFT JOIN face f ON f.image_id = i.id
            LEFT JOIN person p ON p.id = f.person_id
            LEFT JOIN import_session s ON s.id = i.import_id
            WHERE 
        """

        params: List[Any] = []
        where_clauses: List[str] = []

        for idx, crit in enumerate(criteria):
            clause = ""

            # Logic operator (skip for first item)
            if idx > 0:
                op = crit.operator.value
                clause += f" {op} "

            # Filter logic
            if crit.filter_type == FilterType.NAME_FUZZY:
                # value is {"name": "Jon", "threshold": 0.7}
                name = crit.value.get("name", "")
                threshold = crit.value.get("threshold", 0.6)
                # Use an EXISTS per person to allow images with multiple distinct people to satisfy AND logic.
                clause += """
                    EXISTS (
                        SELECT 1
                        FROM face f2
                        JOIN person p2 ON p2.id = f2.person_id
                        WHERE f2.image_id = i.id
                          AND fuzzy_match(p2.primary_name, ?) >= ?
                    )
                """
                params.extend([name, threshold])

            elif crit.filter_type == FilterType.DATE_RANGE:
                # value is {"start": date, "end": date}
                start = crit.value.get("start")
                end = crit.value.get("end")
                # Reusing the robust date logic from previous fix
                shot_expr = """
                    COALESCE(
                        (
                            SELECT value
                            FROM metadata m2
                            WHERE m2.image_id = i.id
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
                        s.import_date
                    )
                """
                date_expr = (
                    f"date(REPLACE(SUBSTR(COALESCE({shot_expr}, '1900-01-01'), 1, 10), ':', '-'))"
                )
                clause += f"({date_expr} BETWEEN ? AND ?)"
                params.extend([start.isoformat(), end.isoformat()])

            elif crit.filter_type == FilterType.PERSON_COUNT:
                # value is {"operator": ">", "count": 2}
                # We need a subquery to count faces per image
                op = crit.value.get("operator", "=")
                count = crit.value.get("count", 0)
                if op not in ("=", ">", "<", ">=", "<="):
                    op = "="

                subquery = f"(SELECT COUNT(*) FROM face WHERE image_id = i.id) {op} ?"
                clause += f"({subquery})"
                params.append(count)

            where_clauses.append(clause)

        sql += "".join(where_clauses)
        sql += " ORDER BY i.id DESC LIMIT 500"  # Cap results for safety

        LOGGER.info(f"Advanced Search SQL: {sql} | Params: {params}")

        try:
            rows = self.conn.execute(sql, params).fetchall()
        except Exception as e:
            LOGGER.error(f"Search failed: {e}")
            return []

        results = []
        for row in rows:
            results.append(
                ImageSearchResult(
                    image_id=row[0],
                    relative_path=row[1],
                    thumbnail_blob=bytes(row[2]) if row[2] else b"",
                    match_reason="Match",  # Placeholder
                )
            )

        return results

    def resolve_image_path(self, relative_path: str) -> Path:
        """Resolve an image path relative to the active DB root."""
        return self.db_root / relative_path
