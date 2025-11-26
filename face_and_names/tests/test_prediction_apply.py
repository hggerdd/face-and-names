from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from face_and_names.services.prediction_apply import apply_predictions
from face_and_names.services.prediction_service import PredictionService


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE face (id INTEGER PRIMARY KEY, face_crop_blob BLOB, image_id INTEGER, person_id INTEGER, predicted_person_id INTEGER, prediction_confidence REAL)")
    conn.execute("CREATE TABLE image (id INTEGER PRIMARY KEY, relative_path TEXT, filename TEXT)")
    conn.execute("INSERT INTO image (id, relative_path, filename) VALUES (1, 'path/to/img.jpg', 'img.jpg')")
    return conn

@pytest.fixture
def service():
    svc = MagicMock(spec=PredictionService)
    return svc

def test_apply_predictions_all(db, service):
    # Setup faces
    db.execute("INSERT INTO face (id, face_crop_blob, image_id) VALUES (1, ?, 1)", (b'face1',))
    db.execute("INSERT INTO face (id, face_crop_blob, image_id) VALUES (2, ?, 1)", (b'face2',))
    db.commit()
    
    # Mock predictions
    service.predict_batch.side_effect = [
        [{"person_id": 10, "confidence": 0.9}],
        [{"person_id": 20, "confidence": 0.8}]
    ]
    
    count = apply_predictions(db, service)
    
    assert count == 2
    rows = db.execute("SELECT id, predicted_person_id, prediction_confidence FROM face ORDER BY id").fetchall()
    assert rows[0] == (1, 10, 0.9)
    assert rows[1] == (2, 20, 0.8)

def test_apply_predictions_unnamed_only(db, service):
    # Face 1 has person_id, Face 2 does not
    db.execute("INSERT INTO face (id, face_crop_blob, image_id, person_id) VALUES (1, ?, 1, 5)", (b'face1',))
    db.execute("INSERT INTO face (id, face_crop_blob, image_id) VALUES (2, ?, 1)", (b'face2',))
    db.commit()
    
    service.predict_batch.return_value = [{"person_id": 20, "confidence": 0.8}]
    
    count = apply_predictions(db, service, unnamed_only=True)
    
    assert count == 1
    # Face 1 should be untouched
    row1 = db.execute("SELECT predicted_person_id FROM face WHERE id=1").fetchone()
    assert row1[0] is None
    # Face 2 should be updated
    row2 = db.execute("SELECT predicted_person_id FROM face WHERE id=2").fetchone()
    assert row2[0] == 20

def test_apply_predictions_assign_person(db, service):
    db.execute("INSERT INTO face (id, face_crop_blob, image_id) VALUES (1, ?, 1)", (b'face1',))
    db.commit()
    
    service.predict_batch.return_value = [{"person_id": 10, "confidence": 0.9}]
    
    apply_predictions(db, service, assign_person=True)
    
    row = db.execute("SELECT person_id, predicted_person_id FROM face WHERE id=1").fetchone()
    assert row[0] == 10  # Assigned
    assert row[1] == 10  # Predicted

def test_cancellation(db, service):
    db.execute("INSERT INTO face (id, face_crop_blob, image_id) VALUES (1, ?, 1)", (b'face1',))
    db.execute("INSERT INTO face (id, face_crop_blob, image_id) VALUES (2, ?, 1)", (b'face2',))
    db.commit()
    
    service.predict_batch.return_value = [{"person_id": 10, "confidence": 0.9}]
    
    # Stop after first
    should_stop = MagicMock(side_effect=[False, True])
    
    count = apply_predictions(db, service, should_stop=should_stop)
    
    assert count == 1
