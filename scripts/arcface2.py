"""
Minimal ArcFace ONNX runner with built-in downloader for arcface_r100_v1.onnx.
Uses onnxruntime directly (no insightface runtime needed).
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

MODEL_URLS = [
    # ONNX model zoo (ArcFace ResNet100)
    "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/arcface/model/arcfaceresnet100-8.onnx",
    "https://github.com/deepinsight/insightface_model_zoo/raw/master/arcface_r100_v1.onnx",
    "https://github.com/deepinsight/insightface/releases/download/v2.0/arcface_r100_v1.onnx",
    "https://github.com/deepinsight/insightface/releases/download/v2.1/arcface_r100_v1.onnx",
    "https://github.com/deepinsight/insightface/releases/download/v0.0/arcface_r100_v1.onnx",
    "https://github.com/deepinsight/insightface/releases/download/v1.0/arcface_r100_v1.onnx",
]
MODEL_NAME = "arcface_r100_v1.onnx"


def ensure_model(path: Path, urls: list[str] | None = None) -> Path:
    """Ensure the ONNX model exists at `path`; download if missing."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    for url in urls or MODEL_URLS:
        try:
            print(f"[info] downloading ArcFace model from {url} to {path}")
            urllib.request.urlretrieve(url, path)
            return path
        except Exception as exc:
            print(f"[warn] download failed from {url}: {exc}", file=sys.stderr)
    print("[error] all downloads failed; provide a manual model path or URL", file=sys.stderr)
    raise RuntimeError("Could not download ArcFace model")


class ArcFaceONNX:
    def __init__(self, model_path: Path, device: str = "cpu", urls: list[str] | None = None):
        providers = ["CPUExecutionProvider"]
        if device == "cuda":
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

        model_file = ensure_model(model_path, urls=urls)
        self.session = ort.InferenceSession(str(model_file), providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def preprocess(self, img: Image.Image) -> np.ndarray:
        img = img.resize((112, 112))
        arr = np.asarray(img, dtype=np.float32)
        arr = (arr - 127.5) / 128.0
        arr = np.transpose(arr, (2, 0, 1))  # CHW
        arr = arr.reshape(1, 3, 112, 112)
        return arr

    def get_embedding(self, img: Image.Image) -> np.ndarray:
        x = self.preprocess(img)
        out = self.session.run([self.output_name], {self.input_name: x})[0]
        emb = out[0]
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    model_path = base / MODEL_NAME
    img_path = base / "face_crop.jpg"
    custom_url = sys.argv[1] if len(sys.argv) > 1 else None
    url_list = [custom_url] if custom_url else None
    if img_path.exists():
        img = Image.open(img_path).convert("RGB")
    else:
        print(f"[warn] {img_path} missing; using random noise")
        img = Image.fromarray((np.random.rand(112, 112, 3) * 255).astype("uint8"))
    model = ArcFaceONNX(model_path, device="cpu", urls=url_list)
    emb = model.get_embedding(img)
    print("Embedding shape:", emb.shape)
    print("First 5 values:", emb[:5])
