from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from face_and_names.services.prediction_service import PredictionService
from face_and_names.training.model_io import ModelBundle


@pytest.fixture
def mock_bundle():
    bundle = MagicMock(spec=ModelBundle)
    bundle.embedder = MagicMock()
    bundle.scaler = MagicMock()
    bundle.classifier = MagicMock()
    bundle.person_ids = [1, 2]
    return bundle

@pytest.fixture
def service(mock_bundle):
    with patch("face_and_names.services.prediction_service.load_artifacts", return_value=mock_bundle):
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
    mock_bundle.classifier.predict_proba.return_value = np.array([
        [0.9, 0.1],  # Class 0 (Person 1)
        [0.2, 0.8]   # Class 1 (Person 2)
    ])
    
    # Create fake image blobs
    img = Image.new("RGB", (10, 10))
    import io
    blob = io.BytesIO()
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
    import io
    blob = io.BytesIO()
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
