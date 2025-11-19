"""
Ingest service scaffold.
Implements folder selection, session tracking, metadata extraction, and detection hooks per docs.
"""

from __future__ import annotations


class IngestService:
    """Placeholder ingest service."""

    def start_session(self, folders: list[str], options: dict | None = None) -> str:
        raise NotImplementedError

    def resume_session(self, session_id: str) -> None:
        raise NotImplementedError

    def cancel(self, session_id: str) -> None:
        raise NotImplementedError
