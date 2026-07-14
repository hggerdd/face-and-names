from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from face_and_names.models.db import initialize_database
from face_and_names.services.embedding_service import (
    EmbeddingIdentity,
    VersionedEmbeddingService,
)


def _make_crop(color: str = "red") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _seed_face(conn, crop: bytes) -> int:
    conn.execute("INSERT INTO import_session (folder_count, image_count) VALUES (?, ?)", (1, 1))
    import_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO image (
            import_id, relative_path, sub_folder, filename,
            content_hash, perceptual_hash, width, height,
            orientation_applied, has_faces, thumbnail_blob, size_bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_id,
            "photos/img.jpg",
            "photos",
            "img.jpg",
            b"\x01" * 32,
            1,
            8,
            8,
            1,
            1,
            b"thumb",
            100,
        ),
    )
    image_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO face (
            image_id, bbox_x, bbox_y, bbox_w, bbox_h,
            bbox_rel_x, bbox_rel_y, bbox_rel_w, bbox_rel_h,
            face_crop_blob, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (image_id, 1.0, 1.0, 4.0, 4.0, 0.1, 0.1, 0.4, 0.4, crop, "detected"),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class CountingEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed_images(self, images):
        self.calls += 1
        vectors = []
        for image in images:
            arr = np.asarray(image, dtype=np.float32)
            vectors.append(arr.mean(axis=(0, 1)))
        return np.asarray(vectors, dtype=np.float32)


def test_versioned_embedding_service_reuses_cached_vectors(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    embedder = CountingEmbedder()
    service = VersionedEmbeddingService(
        conn,
        embedder,
        EmbeddingIdentity(model_name="dummy", model_version="v1"),
    )
    crop = _make_crop()
    face_id = _seed_face(conn, crop)

    first = service.embed_face_blob(face_id, crop)
    second = service.embed_face_blob(face_id, crop)

    assert np.array_equal(first, second)
    assert embedder.calls == 1
    assert conn.execute("SELECT COUNT(*) FROM face_embedding").fetchone()[0] == 1


def test_versioned_embedding_service_recomputes_when_model_version_changes(
    tmp_path: Path,
) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    crop = _make_crop("blue")
    face_id = _seed_face(conn, crop)

    first_embedder = CountingEmbedder()
    VersionedEmbeddingService(
        conn,
        first_embedder,
        EmbeddingIdentity(model_name="dummy", model_version="v1"),
    ).embed_face_blob(face_id, crop)

    second_embedder = CountingEmbedder()
    VersionedEmbeddingService(
        conn,
        second_embedder,
        EmbeddingIdentity(model_name="dummy", model_version="v2"),
    ).embed_face_blob(face_id, crop)

    assert first_embedder.calls == 1
    assert second_embedder.calls == 1
    assert conn.execute("SELECT COUNT(*) FROM face_embedding").fetchone()[0] == 2


def test_versioned_embedding_service_recomputes_when_crop_hash_changes(
    tmp_path: Path,
) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    first_crop = _make_crop("red")
    second_crop = _make_crop("green")
    face_id = _seed_face(conn, first_crop)
    embedder = CountingEmbedder()
    service = VersionedEmbeddingService(
        conn,
        embedder,
        EmbeddingIdentity(model_name="dummy", model_version="v1"),
    )

    service.embed_face_blob(face_id, first_crop)
    service.embed_face_blob(face_id, second_crop)

    assert embedder.calls == 2
    assert conn.execute("SELECT COUNT(*) FROM face_embedding").fetchone()[0] == 2
