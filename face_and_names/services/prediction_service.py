"""
Prediction service backed by persisted model artifacts.
"""

from __future__ import annotations

import io
import logging
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
from PIL import Image

from face_and_names.services.embedding_service import VersionedEmbeddingService
from face_and_names.training.embedding import EmbeddingConfig, EmbeddingModel, FacenetEmbedder
from face_and_names.training.model_io import ModelBundle, load_artifacts

LOGGER = logging.getLogger(__name__)


class PredictionService:
    """Loads classifier + embedder from `model/` and predicts person IDs for face crops."""

    def __init__(
        self,
        model_dir: Path | None = None,
        embedder_factory: Callable[[EmbeddingConfig], EmbeddingModel] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.model_dir = model_dir or Path("model")
        self.embedder_factory = embedder_factory or FacenetEmbedder
        self.conn = conn
        self.bundle: ModelBundle | None = None
        self._load()

    def bind_connection(self, conn: sqlite3.Connection) -> None:
        """Attach a database connection so prediction can reuse versioned embeddings."""
        self.conn = conn

    def _load(self) -> None:
        try:
            self.bundle = load_artifacts(self.model_dir, embedder_factory=self.embedder_factory)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            LOGGER.warning("Prediction model unavailable: %s", exc)
            self.bundle = None

    def predict_batch(
        self,
        face_blobs: Iterable[bytes],
        options: dict | None = None,
        face_ids: Iterable[int] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.bundle:
            raise RuntimeError("Model not loaded")

        blobs = list(face_blobs)
        ids = list(face_ids) if face_ids is not None else None
        if self.conn is not None and ids is not None and len(ids) == len(blobs):
            embedding_service = VersionedEmbeddingService.from_config(
                self.conn,
                self.bundle.embed_config,
                self.bundle.embedder,
            )
            embeddings = embedding_service.embed_face_blobs(zip(ids, blobs))
        else:
            images = [Image.open(io.BytesIO(blob)).convert("RGB") for blob in blobs]
            embeddings = np.asarray(self.bundle.embedder.embed_images(images), dtype=np.float32)
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
            person_id = (
                self.bundle.person_ids[int(pred)] if pred < len(self.bundle.person_ids) else None
            )
            results.append(
                {
                    "person_id": person_id,
                    "confidence": float(confidences[idx]) if confidences[idx] is not None else None,
                }
            )
        return results
