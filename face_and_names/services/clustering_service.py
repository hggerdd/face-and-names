"""
Clustering service implementation using perceptual hashes of face crops.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, List, Sequence

import imagehash
import numpy as np
from PIL import Image
from sklearn.cluster import DBSCAN


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
    last_import_only: bool = False
    folders: Sequence[str] | None = None


class ClusteringService:
    """Cluster faces by similarity and persist cluster IDs."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def cluster_faces(self, options: ClusteringOptions | None = None) -> List[ClusterResult]:
        opts = options or ClusteringOptions()
        faces = list(self._load_faces(opts))
        if not faces:
            return []

        vectors = [self._phash_vector(crop) for _, crop, *_ in faces]
        X = np.stack(vectors)

        if opts.algorithm.lower() == "dbscan":
            labels = self._run_dbscan(X, eps=opts.eps, min_samples=opts.min_samples)
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

    def _phash_vector(self, crop_bytes: bytes) -> np.ndarray:
        with Image.open(BytesIO(crop_bytes)) as img:
            img.load()
            ph = imagehash.phash(img.convert("RGB"))
        # Flatten to 64 bits and cast to float for sklearn
        return np.array(ph.hash, dtype=float).reshape(-1)

    def _run_dbscan(self, X: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
        if len(X) == 1:
            return np.array([0], dtype=int)  # single face, treat as noise/cluster 0
        model = DBSCAN(eps=eps, min_samples=min_samples, metric="hamming")
        return model.fit_predict(X)

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
