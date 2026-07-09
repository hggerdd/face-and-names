"""Controller for settings and maintenance actions."""

from __future__ import annotations

import sqlite3

from face_and_names.services.data_reset import reset_image_data


class SettingsController:
    """Provide maintenance actions for the Settings page."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def reset_imported_data(self) -> None:
        """Delete imported images/faces/metadata while preserving people and groups."""
        reset_image_data(self.conn)
