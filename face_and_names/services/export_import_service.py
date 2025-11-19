"""
Export/Import service scaffold.
"""

from __future__ import annotations


class ExportImportService:
    """Placeholder export/import service."""

    def export(self, scope: dict | None = None) -> object:
        raise NotImplementedError

    def import_data(self, payload: object, dry_run: bool = True) -> object:
        raise NotImplementedError
