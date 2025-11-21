"""
Prediction service backed by persisted model artifacts.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image

from face_and_names.training.embedding import EmbeddingConfig, EmbeddingModel, FacenetEmbedder
from face_and_names.training.model_io import ModelBundle, load_artifacts


class PredictionService:
    """Loads classifier + embedder from `model/` and predicts person IDs for face crops."""

    def __init__(
        self,
        model_dir: Path | None = None,
        embedder_factory: Callable[[EmbeddingConfig], EmbeddingModel] | None = None,
    ) -> None:
        self.model_dir = model_dir or Path("model")
        self.embedder_factory = embedder_factory or FacenetEmbedder
        self.bundle: ModelBundle | None = None
        self._load()

    def _load(self) -> None:
        self.bundle = load_artifacts(self.model_dir, embedder_factory=self.embedder_factory)

    def predict_batch(self, face_blobs: Iterable[bytes], options: dict | None = None) -> list[dict[str, Any]]:
        if not self.bundle:
            raise RuntimeError("Model not loaded")

        images = [Image.open(io.BytesIO(blob)).convert("RGB") for blob in face_blobs]
        embeddings = self.bundle.embedder.embed_images(images)
        X = self.bundle.scaler.transform(embeddings)

        classifier = self.bundle.classifier
        if hasattr(classifier, "predict_proba"):
            probs = classifier.predict_proba(X)
            preds = probs.argmax(axis=1)
            confidences = probs.max(axis=1)
        else:
            preds = classifier.predict(X)
            confidences = [None] * len(preds)

        results = []
        for idx, pred in enumerate(preds):
            person_id = self.bundle.person_ids[int(pred)] if pred < len(self.bundle.person_ids) else None
            results.append({"person_id": person_id, "confidence": float(confidences[idx]) if confidences[idx] is not None else None})
        return results
