"""Versioned embedding cache backed by SQLite."""

from __future__ import annotations

import hashlib
import io
import sqlite3
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from PIL import Image

from face_and_names.models.repositories import FaceEmbeddingRepository
from face_and_names.training.embedding import EmbeddingConfig, EmbeddingModel, FacenetEmbedder


@dataclass(frozen=True)
class EmbeddingIdentity:
    """Stable identity for an embedding backbone/configuration."""

    model_name: str
    model_version: str
    preprocessing_version: str = "face-crop-v1"
    input_normalization: str = "inception-resnet-v1"
    similarity_metric: str = "cosine"
    crop_strategy: str = "padded-square-224"


class VersionedEmbeddingService:
    """Compute embeddings and cache them by face, model version, and crop hash."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        embedder: EmbeddingModel,
        identity: EmbeddingIdentity,
    ) -> None:
        self.conn = conn
        self.embedder = embedder
        self.identity = identity
        self.repo = FaceEmbeddingRepository(conn)

    @classmethod
    def from_config(
        cls,
        conn: sqlite3.Connection,
        config: EmbeddingConfig,
        embedder: EmbeddingModel | None = None,
    ) -> "VersionedEmbeddingService":
        """Build a cache service for the configured embedding model."""
        return cls(
            conn=conn,
            embedder=embedder or FacenetEmbedder(config),
            identity=EmbeddingIdentity(
                model_name=config.model_name,
                model_version=config.version_id(),
                input_normalization=("inception-resnet-v1" if config.normalize else "0-1"),
                crop_strategy=f"square-{config.image_size}",
            ),
        )

    def embed_face_blob(self, face_id: int, crop_blob: bytes) -> np.ndarray:
        """Return one embedding, reading from cache when possible."""
        return self.embed_face_blobs([(face_id, crop_blob)])[0]

    def embed_face_blobs(self, faces: Iterable[tuple[int, bytes]]) -> np.ndarray:
        """Return embeddings in input order, computing and caching missing rows in a batch."""
        face_items = list(faces)
        if not face_items:
            return np.zeros((0, 0), dtype=np.float32)

        result: list[np.ndarray | None] = []
        missing: list[tuple[int, bytes, str, int]] = []
        for index, (face_id, crop_blob) in enumerate(face_items):
            crop_hash = self.crop_sha256(crop_blob)
            cached = self.repo.get(
                face_id=face_id,
                model_name=self.identity.model_name,
                model_version=self.identity.model_version,
                crop_sha256=crop_hash,
                preprocessing_version=self.identity.preprocessing_version,
                input_normalization=self.identity.input_normalization,
                similarity_metric=self.identity.similarity_metric,
                crop_strategy=self.identity.crop_strategy,
            )
            if cached is not None:
                result.append(self._deserialize(cached.vector_blob, cached.vector_dim))
                continue
            result.append(None)
            missing.append((face_id, crop_blob, crop_hash, index))

        if missing:
            images = [self._decode_crop(crop_blob) for _, crop_blob, _, _ in missing]
            computed = np.asarray(self.embedder.embed_images(images), dtype=np.float32)
            for vector, (face_id, _crop_blob, crop_hash, index) in zip(computed, missing):
                vector = np.asarray(vector, dtype=np.float32)
                self.repo.upsert(
                    face_id=face_id,
                    model_name=self.identity.model_name,
                    model_version=self.identity.model_version,
                    crop_sha256=crop_hash,
                    vector_dim=int(vector.shape[0]),
                    vector_dtype="float32",
                    vector_blob=self._serialize(vector),
                    preprocessing_version=self.identity.preprocessing_version,
                    input_normalization=self.identity.input_normalization,
                    similarity_metric=self.identity.similarity_metric,
                    crop_strategy=self.identity.crop_strategy,
                )
                result[index] = vector

        return np.stack([vec for vec in result if vec is not None], axis=0)

    @staticmethod
    def crop_sha256(crop_blob: bytes) -> str:
        """Return a stable content hash for an encoded face crop."""
        return hashlib.sha256(crop_blob).hexdigest()

    @staticmethod
    def _decode_crop(crop_blob: bytes) -> Image.Image:
        with Image.open(io.BytesIO(crop_blob)) as image:
            image.load()
            return image.convert("RGB")

    @staticmethod
    def _serialize(vector: np.ndarray) -> bytes:
        return np.ascontiguousarray(vector, dtype=np.float32).tobytes()

    @staticmethod
    def _deserialize(vector_blob: bytes, vector_dim: int) -> np.ndarray:
        vector = np.frombuffer(vector_blob, dtype=np.float32)
        if vector_dim <= 0 or vector.size != vector_dim:
            raise ValueError(
                f"Invalid cached embedding dimensions: metadata={vector_dim}, bytes={vector.size}"
            )
        return vector.reshape(vector_dim).copy()
