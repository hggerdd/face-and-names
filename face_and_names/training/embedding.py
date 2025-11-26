"""
Embedding helpers.

Provides a reusable Facenet-based embedder plus config dataclass. The interface
is intentionally simple (`embed_images -> np.ndarray`) to allow test doubles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol

import numpy as np
import torch
from facenet_pytorch import InceptionResnetV1
from PIL import Image


@dataclass
class EmbeddingConfig:
    model_name: str = "inception_resnet_v1"
    pretrained: str = "vggface2"
    image_size: int = 160
    normalize: bool = True
    device: str | None = None


class EmbeddingModel(Protocol):
    def embed_images(self, images: List[Image.Image]) -> np.ndarray: ...


class FacenetEmbedder:
    """Thin wrapper around facenet-pytorch InceptionResnetV1."""

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or EmbeddingConfig()
        device_name = self.config.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device(device_name)
        self.model = InceptionResnetV1(pretrained=self.config.pretrained).eval().to(self.device)

    def _preprocess(self, image: Image.Image) -> torch.Tensor:
        cfg = self.config
        img = image.resize((cfg.image_size, cfg.image_size))
        arr = np.asarray(img, dtype=np.float32)
        if arr.ndim == 2:  # grayscale fallback
            arr = np.stack([arr, arr, arr], axis=-1)
        if cfg.normalize:
            arr = (arr - 127.5) / 128.0  # scale to roughly [-1,1]
        else:
            arr = arr / 255.0
        tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(self.device)
        return tensor

    def embed_images(self, images: List[Image.Image]) -> np.ndarray:
        if not images:
            return np.zeros((0, 512), dtype=np.float32)
        tensors = torch.cat([self._preprocess(img) for img in images], dim=0)
        with torch.no_grad():
            emb = self.model(tensors)
        return emb.cpu().numpy()
