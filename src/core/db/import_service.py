from __future__ import annotations

import logging

from .context import DatabaseContext


class ImportService:
    """Handles bookkeeping for imports history."""

    def __init__(self, context: DatabaseContext):
        self._context = context

    def start_new_import(self, folder_count: int) -> int | None:
        try:
            with self._context.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO imports (folder_count, image_count)
                    VALUES (?, 0)
                    """,
                    (folder_count,),
                )
                import_id = cursor.lastrowid
                logging.info("Started new import session with ID: %s", import_id)
                return import_id
        except Exception as exc:
            logging.error("Error starting new import: %s", exc)
            return None

    def update_image_count(self, import_id: int, image_count: int) -> bool:
        try:
            with self._context.transaction() as cursor:
                cursor.execute(
                    """
                    UPDATE imports
                    SET image_count = ?
                    WHERE import_id = ?
                    """,
                    (image_count, import_id),
                )
            return True
        except Exception as exc:
            logging.error("Error updating import image count: %s", exc)
            return False
