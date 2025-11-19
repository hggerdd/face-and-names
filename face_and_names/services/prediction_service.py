"""
Prediction service scaffold (see docs/model_runner.md and docs/service_contracts.md).
"""

from __future__ import annotations


class PredictionService:
    """Placeholder prediction service."""

    def predict_batch(self, faces: list[object], options: dict | None = None) -> list[object]:
        raise NotImplementedError
