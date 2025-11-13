from __future__ import annotations

import logging
from typing import Dict, Tuple

from .context import DatabaseContext


class MetadataService:
    """Persists image metadata entries."""

    def __init__(self, context: DatabaseContext):
        self._context = context

    def save_image_metadata(self, image_id: int, metadata: Dict[str, Tuple[str, str]]) -> bool:
        """Replace metadata for an image."""
        try:
            with self._context.transaction() as cursor:
                cursor.execute("DELETE FROM image_metadata WHERE image_id = ?", (image_id,))
                cursor.executemany(
                    """
                    INSERT INTO image_metadata (image_id, meta_key, meta_type, meta_value)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (image_id, key, meta_type, str(value))
                        for key, (meta_type, value) in metadata.items()
                    ],
                )
            return True
        except Exception as exc:
            logging.error("Error saving metadata: %s", exc)
            return False
