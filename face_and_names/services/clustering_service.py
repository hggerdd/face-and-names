"""
Clustering service implementation using perceptual hashes of face crops.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, List, Sequence
import logging
from pathlib import Path
import urllib.request

import imagehash
import numpy as np
from PIL import Image, ImageOps
from sklearn.cluster import DBSCAN, KMeans
import torch
from facenet_pytorch import InceptionResnetV1

LOGGER = logging.getLogger(__name__)

ARCFACE_MODEL_NAME = "arcface_r100_v1.onnx"
ARCFACE_MODEL_URLS = [
    # ONNX model zoo (ArcFace ResNet100)
    "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/arcface/model/arcfaceresnet100-8.onnx",
    "https://github.com/deepinsight/insightface_model_zoo/raw/master/arcface_r100_v1.onnx",
    "https://github.com/deepinsight/insightface/releases/download/v2.0/arcface_r100_v1.onnx",
    "https://github.com/deepinsight/insightface/releases/download/v2.1/arcface_r100_v1.onnx",
    "https://github.com/deepinsight/insightface/releases/download/v0.0/arcface_r100_v1.onnx",
    "https://github.com/deepinsight/insightface/releases/download/v1.0/arcface_r100_v1.onnx",
]


@dataclass
class ClusteredFace:
    face_id: int
    crop: bytes
    person_name: str | None
    predicted_name: str | None
    confidence: float | None


@dataclass
class ClusterResult:
    cluster_id: int
    faces: list[ClusteredFace]
    is_noise: bool = False


@dataclass
class ClusteringOptions:
    algorithm: str = "dbscan"
    eps: float = 0.25  # Hamming distance threshold on normalized bits
    min_samples: int = 1
    k_clusters: int = 50
    last_import_only: bool = False
    folders: Sequence[str] | None = None
    feature_source: str = "phash"  # phash, phash_raw, raw, embedding, arcface
    normalize_faces: bool = True
    gamma: float = 1.0
    exclude_named: bool = False


class ClusteringService:
    """Cluster faces by similarity and persist cluster IDs."""

    def __init__(self, conn) -> None:
        self.conn = conn
        self._embed_model: InceptionResnetV1 | None = None
        self._arcface_model = None
        self._arcface_recognizer = None
        self._arcface_session = None
        self._arcface_io: tuple[str, str] | None = None
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def cluster_faces(self, options: ClusteringOptions | None = None) -> List[ClusterResult]:
        opts = options or ClusteringOptions()
        faces = list(self._load_faces(opts))
        if not faces:
            return []

        vectors = [self._feature_vector(crop, opts) for _, crop, *_ in faces]
        X = np.stack(vectors)

        algo = opts.algorithm.lower()
        if algo == "dbscan":
            labels = self._run_dbscan(X, eps=opts.eps, min_samples=int(opts.min_samples))
        elif algo == "kmeans":
            labels = self._run_kmeans(X, n_clusters=int(opts.k_clusters))
        else:
            raise ValueError(f"Unsupported algorithm: {opts.algorithm}")

        # Renumber clusters sequentially; noise as 0
        renumbered = self._renumber_labels(labels)
        self._persist_cluster_ids(faces, renumbered)

        results: list[ClusterResult] = []
        grouped: dict[int, list[int]] = {}
        for idx, cid in enumerate(renumbered):
            grouped.setdefault(cid, []).append(idx)

        for cid, idxs in grouped.items():
            clustered_faces = [
                ClusteredFace(
                    face_id=faces[i][0],
                    crop=faces[i][1],
                    person_name=faces[i][2],
                    predicted_name=faces[i][3],
                    confidence=faces[i][4],
                )
                for i in idxs
            ]
            results.append(ClusterResult(cluster_id=cid, faces=clustered_faces, is_noise=(cid == 0)))

        results.sort(key=lambda c: (c.is_noise, c.cluster_id))
        return results

    def _load_faces(self, opts: ClusteringOptions) -> Iterable[tuple]:
        params: list = []
        filters: list[str] = []

        if opts.last_import_only:
            last_import = self.conn.execute("SELECT MAX(id) FROM import_session").fetchone()[0]
            if last_import is not None:
                filters.append("i.import_id = ?")
                params.append(last_import)
        if opts.folders:
            placeholders = ", ".join("?" for _ in opts.folders)
            filters.append(f"i.sub_folder IN ({placeholders})")
            params.extend(opts.folders)
        if opts.exclude_named:
            filters.append("f.person_id IS NULL")

        where_clause = ""
        if filters:
            where_clause = "WHERE " + " AND ".join(filters)

        rows = self.conn.execute(
            f"""
            SELECT
                f.id,
                f.face_crop_blob,
                p.primary_name AS person_name,
                pp.primary_name AS predicted_name,
                f.prediction_confidence
            FROM face f
            JOIN image i ON i.id = f.image_id
            LEFT JOIN person p ON p.id = f.person_id
            LEFT JOIN person pp ON pp.id = f.predicted_person_id
            {where_clause}
            """,
            params,
        ).fetchall()
        for row in rows:
            if row[1] is None:
                continue
            yield (int(row[0]), bytes(row[1]), row[2], row[3], row[4])

    def _feature_vector(self, crop_bytes: bytes, opts: ClusteringOptions) -> np.ndarray:
        with Image.open(BytesIO(crop_bytes)) as img:
            img.load()
            if opts.feature_source == "phash":
                ph = imagehash.phash(self._preprocess_for_hash(img, opts))
                return np.array(ph.hash, dtype=float).reshape(-1)
            elif opts.feature_source == "phash_raw":
                ph = imagehash.phash(img.convert("RGB"))
                return np.array(ph.hash, dtype=float).reshape(-1)
            elif opts.feature_source == "raw":
                return self._raw_vector(img, opts)
            elif opts.feature_source == "embedding":
                return self._embedding_vector(img, opts)
            elif opts.feature_source == "arcface":
                return self._arcface_vector(img, opts)
            else:
                raise ValueError(f"Unsupported feature_source: {opts.feature_source}")

    def _preprocess_for_hash(self, img: Image.Image, opts: ClusteringOptions) -> Image.Image:
        """
        Normalize lighting to reduce variance between dark/light faces:
        - convert to grayscale
        - apply autocontrast
        - optional gamma correction
        """
        gray = img.convert("L")
        norm = ImageOps.autocontrast(gray)
        if opts.gamma and opts.gamma != 1.0:
            norm = ImageOps.gamma(norm, opts.gamma)
        return norm

    def _raw_vector(self, img: Image.Image, opts: ClusteringOptions) -> np.ndarray:
        """Downscale raw face image to fixed size and flatten."""
        target = 32
        proc = img.convert("RGB")
        if opts.normalize_faces:
            proc = ImageOps.autocontrast(proc)
            if opts.gamma and opts.gamma != 1.0:
                proc = ImageOps.gamma(proc, opts.gamma)
        proc = proc.resize((target, target), Image.Resampling.BILINEAR)
        arr = np.asarray(proc, dtype=np.float32) / 255.0
        return arr.reshape(-1)

    def _embedding_vector(self, img: Image.Image, opts: ClusteringOptions) -> np.ndarray:
        """Compute FaceNet embedding for clustering."""
        model = self._load_embed_model()
        proc = img.convert("RGB").resize((160, 160), Image.Resampling.LANCZOS)
        arr = np.asarray(proc, dtype=np.float32)
        arr = (arr - 127.5) / 128.0
        tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(self._device)
        with torch.no_grad():
            emb = model(tensor)
        vec = emb.cpu().numpy().reshape(-1)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def _load_embed_model(self) -> InceptionResnetV1:
        if self._embed_model is None:
            self._embed_model = InceptionResnetV1(pretrained="vggface2").eval().to(self._device)
        return self._embed_model

    def _arcface_vector(self, img: Image.Image, opts: ClusteringOptions) -> np.ndarray:
        """
        Compute ArcFace embedding for clustering.
        Requires `insightface`; falls back to FaceNet embedding if unavailable.
        """
        try:
            import numpy as _np
            import insightface  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.warning("ArcFace embedding unavailable (insightface missing): %s; using FaceNet", exc)
            return self._embedding_vector(img, opts)

        if self._arcface_session is None:
            if not self._load_arcface_onnx():
                return self._embedding_vector(img, opts)

        proc = img.convert("RGB").resize((112, 112), Image.Resampling.BILINEAR)
        arr = np.asarray(proc, dtype=np.float32)
        arr = (arr - 127.5) / 128.0
        arr = np.transpose(arr, (2, 0, 1))  # CHW
        arr = arr.reshape(1, 3, 112, 112)
        try:
            inp, out = self._arcface_io or ("data", "fc1")
            res = self._arcface_session.run([out], {inp: arr})
            emb = res[0][0]
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("ArcFace ONNX embedding failed: %s; using FaceNet", exc)
            return self._embedding_vector(img, opts)
        vec = np.asarray(emb, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def _load_arcface_onnx(self) -> bool:
        """Load ArcFace ONNX model via onnxruntime; returns True on success."""
        try:
            import onnxruntime as ort  # type: ignore
        except Exception as exc:
            LOGGER.warning("ArcFace ONNX runtime missing: %s; using FaceNet", exc)
            return False

        model_path = Path(ARCFACE_MODEL_NAME)
        if not model_path.exists():
            if not self._download_arcface_model(model_path):
                return False

        providers = ["CPUExecutionProvider"]
        try:
            session = ort.InferenceSession(str(model_path), providers=providers)
            inp = session.get_inputs()[0].name
            out = session.get_outputs()[0].name
            self._arcface_session = session
            self._arcface_io = (inp, out)
            return True
        except Exception as exc:
            LOGGER.warning("ArcFace ONNX load failed: %s; using FaceNet", exc)
            return False

    def _download_arcface_model(self, path: Path) -> bool:
        for url in ARCFACE_MODEL_URLS:
            try:
                LOGGER.info("Downloading ArcFace model from %s", url)
                path.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(url, path)
                return True
            except Exception as exc:
                LOGGER.warning("Download failed from %s: %s", url, exc)
        LOGGER.error("All ArcFace model downloads failed; place %s manually", path)
        return False

    def _run_dbscan(self, X: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
        if len(X) == 1:
            return np.array([0], dtype=int)  # single face, treat as noise/cluster 0
        model = DBSCAN(eps=eps, min_samples=min_samples, metric="hamming")
        return model.fit_predict(X)

    def _run_kmeans(self, X: np.ndarray, n_clusters: int) -> np.ndarray:
        if len(X) == 0:
            return np.array([], dtype=int)
        n_clusters = max(1, min(n_clusters, len(X)))
        model = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
        labels = model.fit_predict(X)
        # shift labels to start at 1; kmeans has no noise notion, so 0 is a valid cluster
        return labels + 1

    def _renumber_labels(self, labels: np.ndarray) -> list[int]:
        mapping: dict[int, int] = {}
        next_label = 1
        renumbered: list[int] = []
        for lbl in labels.tolist():
            if lbl == -1:
                renumbered.append(0)
                continue
            if lbl not in mapping:
                mapping[lbl] = next_label
                next_label += 1
            renumbered.append(mapping[lbl])
        return renumbered

    def _persist_cluster_ids(self, faces: list[tuple], cluster_ids: list[int]) -> None:
        rows = [(cid, face_id) for (face_id, *_), cid in zip(faces, cluster_ids)]
        self.conn.executemany("UPDATE face SET cluster_id = ? WHERE id = ?", rows)
        self.conn.commit()
