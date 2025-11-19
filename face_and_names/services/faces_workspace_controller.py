"""
Faces workspace controller scaffold.
"""

from __future__ import annotations


class FacesWorkspaceController:
    """Placeholder faces workspace controller."""

    def load_faces(self, filters: dict | None = None) -> list[object]:
        raise NotImplementedError

    def accept_predictions(self, face_ids: list[int]) -> None:
        raise NotImplementedError
