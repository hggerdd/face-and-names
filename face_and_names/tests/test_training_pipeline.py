from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image
from sklearn.neighbors import KNeighborsClassifier

from face_and_names.models.db import initialize_database
from face_and_names.training.data_loader import load_verified_faces
from face_and_names.training.model_io import load_artifacts
from face_and_names.training.trainer import TrainingConfig, train_model_from_db
from face_and_names.services.prediction_service import PredictionService


def _make_image_bytes(color: str) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _insert_import_and_image(conn):
    conn.execute("INSERT INTO import_session (folder_count, image_count) VALUES (?, ?)", (1, 0))
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
            b"\x00" * 32,
            1,
            10,
            10,
            1,
            1,
            b"\x00\x01",
            123,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _insert_face(conn, image_id: int, person_id: int, blob: bytes) -> None:
    conn.execute(
        """
        INSERT INTO face (
            image_id, bbox_x, bbox_y, bbox_w, bbox_h,
            bbox_rel_x, bbox_rel_y, bbox_rel_w, bbox_rel_h,
            face_crop_blob, cluster_id, person_id, predicted_person_id,
            prediction_confidence, provenance
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            image_id,
            1.0,
            1.0,
            2.0,
            2.0,
            0.1,
            0.1,
            0.2,
            0.2,
            blob,
            None,
            person_id,
            None,
            None,
            "manual",
        ),
    )


class DummyEmbedder:
    """Deterministic, lightweight embedder for tests."""

    def embed_images(self, images):
        vectors = []
        for img in images:
            arr = np.asarray(img, dtype=np.float32)
            r = float(arr[..., 0].mean())
            g = float(arr[..., 1].mean())
            b = float(arr[..., 2].mean())
            vectors.append(np.array([r, g, b], dtype=np.float32))
        return np.stack(vectors, axis=0)


def _dummy_embedder_factory(cfg) -> DummyEmbedder:  # noqa: ARG001
    return DummyEmbedder()


def test_load_verified_faces_returns_named_rows(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    # create minimal person and face row
    conn.execute(
        "INSERT INTO person (id, primary_name, first_name, last_name) VALUES (?, ?, ?, ?)",
        (1, "One", "One", ""),
    )
    image_id = _insert_import_and_image(conn)
    blob = _make_image_bytes("red")
    _insert_face(conn, image_id, person_id=1, blob=blob)
    conn.commit()

    samples = load_verified_faces(conn)
    assert len(samples) == 1
    assert samples[0].person_id == 1


def test_train_and_predict_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "faces.db"
    conn = initialize_database(db_path)
    conn.execute(
        "INSERT INTO person (id, primary_name, first_name, last_name) VALUES (?, ?, ?, ?)",
        (1, "One", "One", ""),
    )
    conn.execute(
        "INSERT INTO person (id, primary_name, first_name, last_name) VALUES (?, ?, ?, ?)",
        (2, "Two", "Two", ""),
    )
    image_id = _insert_import_and_image(conn)
    red_blob = _make_image_bytes("red")
    blue_blob = _make_image_bytes("blue")
    _insert_face(conn, image_id, person_id=1, blob=red_blob)
    _insert_face(conn, image_id, person_id=1, blob=_make_image_bytes("red"))
    _insert_face(conn, image_id, person_id=2, blob=blue_blob)
    _insert_face(conn, image_id, person_id=2, blob=_make_image_bytes("blue"))
    conn.commit()

    cfg = TrainingConfig(model_dir=tmp_path / "model")
    metrics = train_model_from_db(
        db_path,
        config=cfg,
        embedder=DummyEmbedder(),
        classifier_factory=lambda: KNeighborsClassifier(n_neighbors=1),
    )
    assert metrics["classes"] == 2
    assert metrics["samples"] == 4

    bundle = load_artifacts(cfg.model_dir, embedder_factory=_dummy_embedder_factory)
    assert bundle.person_ids == [1, 2] or bundle.person_ids == [2, 1]

    service = PredictionService(model_dir=cfg.model_dir, embedder_factory=_dummy_embedder_factory)
    results = service.predict_batch([red_blob, blue_blob])
    assert len(results) == 2
    assert {r["person_id"] for r in results} == {1, 2}
