from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from face_and_names.models.db import initialize_database
from face_and_names.services.prediction_service import PredictionService
from face_and_names.training.embedding import EmbeddingConfig
from face_and_names.training.model_io import ModelBundle


@pytest.fixture
def mock_bundle():
    bundle = MagicMock(spec=ModelBundle)
    bundle.embed_config = EmbeddingConfig(model_name="dummy", pretrained="test", image_size=8)
    bundle.embedder = MagicMock()
    bundle.scaler = MagicMock()
    bundle.classifier = MagicMock()
    bundle.person_ids = [1, 2]
    return bundle


@pytest.fixture
def service(mock_bundle):
    with patch(
        "face_and_names.services.prediction_service.load_artifacts", return_value=mock_bundle
    ):
        yield PredictionService()


def test_init_loads_artifacts():
    with patch("face_and_names.services.prediction_service.load_artifacts") as mock_load:
        PredictionService()
        mock_load.assert_called_once()


def test_predict_batch_success(service, mock_bundle):
    # Mock embeddings
    mock_bundle.embedder.embed_images.return_value = np.zeros((2, 128))
    # Mock scaler
    mock_bundle.scaler.transform.return_value = np.zeros((2, 128))
    # Mock classifier probabilities
    mock_bundle.classifier.predict_proba.return_value = np.array(
        [
            [0.9, 0.1],  # Class 0 (Person 1)
            [0.2, 0.8],  # Class 1 (Person 2)
        ]
    )

    # Create fake image blobs
    img = Image.new("RGB", (10, 10))

    blob = BytesIO()
    img.save(blob, format="JPEG")
    blob_bytes = blob.getvalue()

    results = service.predict_batch([blob_bytes, blob_bytes])

    assert len(results) == 2
    assert results[0]["person_id"] == 1
    assert results[0]["confidence"] == 0.9
    assert results[1]["person_id"] == 2
    assert results[1]["confidence"] == 0.8


def test_predict_batch_no_proba(service, mock_bundle):
    # Test classifier without predict_proba (e.g. SVM without probability)
    del mock_bundle.classifier.predict_proba
    mock_bundle.classifier.predict.return_value = np.array([0, 1])
    mock_bundle.embedder.embed_images.return_value = np.zeros((2, 128))
    mock_bundle.scaler.transform.return_value = np.zeros((2, 128))

    img = Image.new("RGB", (10, 10))

    blob = BytesIO()
    img.save(blob, format="JPEG")
    blob_bytes = blob.getvalue()

    results = service.predict_batch([blob_bytes, blob_bytes])

    assert len(results) == 2
    assert results[0]["person_id"] == 1
    assert results[0]["confidence"] is None
    assert results[1]["person_id"] == 2


def test_predict_batch_not_loaded():
    service = PredictionService()
    service.bundle = None
    with pytest.raises(RuntimeError, match="Model not loaded"):
        service.predict_batch([])


def _seed_face(conn, crop_blob: bytes) -> int:
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
            b"\x07" * 32,
            1,
            10,
            10,
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
        (image_id, 1.0, 1.0, 4.0, 4.0, 0.1, 0.1, 0.4, 0.4, crop_blob, "detected"),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_predict_batch_reuses_versioned_embeddings_with_face_ids(
    mock_bundle, tmp_path: Path
) -> None:
    conn = initialize_database(tmp_path / "faces.db")
    img = Image.new("RGB", (10, 10), color="red")
    blob = BytesIO()
    img.save(blob, format="JPEG")
    crop_blob = blob.getvalue()
    face_id = _seed_face(conn, crop_blob)
    mock_bundle.embedder.embed_images.return_value = np.ones((1, 3), dtype=np.float32)
    mock_bundle.scaler.transform.return_value = np.zeros((1, 3), dtype=np.float32)
    mock_bundle.classifier.predict_proba.return_value = np.array([[1.0, 0.0]])

    with patch(
        "face_and_names.services.prediction_service.load_artifacts", return_value=mock_bundle
    ):
        service = PredictionService(conn=conn)

    first = service.predict_batch([crop_blob], face_ids=[face_id])
    second = service.predict_batch([crop_blob], face_ids=[face_id])

    assert first == second == [{"person_id": 1, "confidence": 1.0}]
    assert mock_bundle.embedder.embed_images.call_count == 1
    assert conn.execute("SELECT COUNT(*) FROM face_embedding").fetchone()[0] == 1
