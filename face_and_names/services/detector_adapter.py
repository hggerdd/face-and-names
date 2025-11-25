"""
YOLO-based detector adapter (see docs/detector_adapter.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Sequence, Tuple


@dataclass
class FaceDetection:
    """Represents one detected face."""

    bbox_abs: Tuple[float, float, float, float]
    bbox_rel: Tuple[float, float, float, float]
    confidence: float
    crop: Any | None = None


class DetectorAdapter:
    """YOLO detector adapter."""

    def __init__(self, weights_path: Path, device: str | None = None) -> None:
        self.weights_path = Path(weights_path)
        self.device = device
        self._model: Any | None = None

    def load(self) -> None:
        """Load YOLO model from weights path."""
        if not self.weights_path.exists():
            raise FileNotFoundError(f"Detector weights not found: {self.weights_path}")
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "ultralytics/cv2 not available. Install opencv-python and ultralytics (uv sync) to enable detection."
            ) from exc

        self._model = YOLO(str(self.weights_path))

    def detect_batch(self, images: Sequence[Any]) -> List[List[FaceDetection]]:
        """
        Run detection on a batch of images.
        Images can be numpy arrays, PIL images, or paths as supported by ultralytics.
        """
        if self._model is None:
            raise RuntimeError("Detector not loaded. Call load() first.")

        results = self._model.predict(images, device=self.device, verbose=False)
        detections: List[List[FaceDetection]] = []

        for result in results:
            width, height = self._get_dimensions(result)
            faces: List[FaceDetection] = []
            if result.boxes is None or result.boxes.xyxy is None:
                detections.append(faces)
                continue

            for box, conf in zip(result.boxes.xyxy, result.boxes.conf):
                x1, y1, x2, y2 = map(float, box.tolist())
                x1, y1, x2, y2 = self._clamp_box(x1, y1, x2, y2, width, height)
                w = x2 - x1
                h = y2 - y1
                bbox_abs = (x1, y1, w, h)
                bbox_rel = (
                    x1 / width if width else 0.0,
                    y1 / height if height else 0.0,
                    w / width if width else 0.0,
                    h / height if height else 0.0,
                )
                faces.append(
                    FaceDetection(
                        bbox_abs=bbox_abs,
                        bbox_rel=bbox_rel,
                        confidence=float(conf.item()),
                        crop=None,  # cropping handled elsewhere
                    )
                )
            detections.append(faces)

        return detections

    @staticmethod
    def _get_dimensions(result: Any) -> Tuple[float, float]:
        """Extract width/height from an ultralytics Result."""
        if not hasattr(result, "orig_shape"):
            return 0.0, 0.0
        height, width = result.orig_shape
        return float(width), float(height)

    @staticmethod
    def _clamp_box(
        x1: float, y1: float, x2: float, y2: float, width: float, height: float
    ) -> Tuple[float, float, float, float]:
        """Clamp bbox coordinates to image bounds."""
        x1 = max(0.0, min(x1, width))
        y1 = max(0.0, min(y1, height))
        x2 = max(0.0, min(x2, width))
        y2 = max(0.0, min(y2, height))
        return x1, y1, x2, y2
