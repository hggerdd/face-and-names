"""
Repository scaffolds for database access.
"""

from __future__ import annotations


class ImageRepository:
    def __init__(self, conn) -> None:
        self.conn = conn

    def add(self, record: dict) -> int:
        raise NotImplementedError


class FaceRepository:
    def __init__(self, conn) -> None:
        self.conn = conn

    def add(self, record: dict) -> int:
        raise NotImplementedError
