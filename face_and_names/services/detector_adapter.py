"""
Detector adapter scaffold (see docs/detector_adapter.md).
"""

from __future__ import annotations


class DetectorAdapter:
    """Placeholder detector adapter."""

    def load(self, device: str | None = None) -> None:
        raise NotImplementedError

    def detect_batch(self, images: list[object]) -> list[list[object]]:
        raise NotImplementedError
