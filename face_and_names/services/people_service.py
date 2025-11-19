"""
People and groups management scaffold.
"""

from __future__ import annotations


class PeopleService:
    """Placeholder people service."""

    def create_person(self, name: str, aliases: list[str] | None = None) -> int:
        raise NotImplementedError

    def merge_people(self, source_ids: list[int], target_id: int) -> None:
        raise NotImplementedError
