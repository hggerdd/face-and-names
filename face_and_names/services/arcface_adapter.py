"""Explicit, offline-only ArcFace ONNX adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image


class FaceEmbeddingRunner(Protocol):
    """Boundary used by clustering for a face embedding model."""

    def embed(self, image: Image.Image) -> np.ndarray: ...


class ArcFaceOnnxRunner:
    """Run an ArcFace ONNX model already installed by the user."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self._session = None
        self._input_name: str | None = None
        self._output_name: str | None = None

    def _load(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError(f"ArcFace model not found: {self.model_path}")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("onnxruntime is required for ArcFace clustering") from exc
        session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if not inputs or not outputs:
            raise ValueError(f"ArcFace model has no usable inputs/outputs: {self.model_path}")
        self._session = session
        self._input_name = inputs[0].name
        self._output_name = outputs[0].name

    def embed(self, image: Image.Image) -> np.ndarray:
        if self._session is None:
            self._load()
        assert self._session is not None
        assert self._input_name is not None
        assert self._output_name is not None
        proc = image.convert("RGB").resize((112, 112), Image.Resampling.BILINEAR)
        arr = np.asarray(proc, dtype=np.float32)
        arr = np.transpose((arr - 127.5) / 128.0, (2, 0, 1))[None, ...]
        result = self._session.run([self._output_name], {self._input_name: arr})[0]
        vector = np.asarray(result, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector
