from __future__ import annotations

import threading
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageFile

from face_and_names.models.db import initialize_database
from face_and_names.services.ingest_service import IngestOptions, IngestService

ImageFile.LOAD_TRUNCATED_IMAGES = True


def _make_image(path: Path, size: tuple[int, int], orientation: int | None = None, color: str = "red") -> None:
    image = Image.new("RGB", size, color=color)
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", exif=exif.tobytes())


def test_ingest_imports_images_and_thumbnails(tmp_path: Path) -> None:
    db_root = tmp_path / "dbroot"
    photos = db_root / "photos"
    img1 = photos / "a.jpg"
    img2 = photos / "nested" / "b.jpg"
    _make_image(img1, (10, 20), orientation=6)  # rotated via EXIF
    _make_image(img2, (30, 40))

    conn = initialize_database(db_root / "faces.db")
    ingest = IngestService(db_root=db_root, conn=conn)

    progress = ingest.start_session([photos], options=IngestOptions(recursive=True))

    assert progress.processed == 2
    assert progress.skipped_existing == 0
    assert progress.total == 2
    assert progress.errors == []

    image_rows = conn.execute(
        "SELECT relative_path, sub_folder, width, height, thumbnail_blob FROM image ORDER BY id"
    ).fetchall()
    # Orientation applied: width/height swapped
    assert image_rows[0][0].endswith("photos/a.jpg")
    assert (image_rows[0][2], image_rows[0][3]) == (20, 10)
    thumb_blob = image_rows[0][4]
    assert isinstance(thumb_blob, bytes)
    assert len(thumb_blob) > 0

    assert image_rows[1][0].endswith("photos/nested/b.jpg")

    meta_count = conn.execute("SELECT COUNT(*) FROM metadata").fetchone()[0]
    assert meta_count >= 1  # Orientation tag present

    import_count = conn.execute("SELECT image_count FROM import_session WHERE id = 1").fetchone()[0]
    assert import_count == 2


def test_ingest_skips_duplicates_by_content_hash(tmp_path: Path) -> None:
    db_root = tmp_path / "dbroot"
    photos = db_root / "photos"
    img1 = photos / "dup1.jpg"
    img2 = photos / "dup2.jpg"
    _make_image(img1, (16, 16))
    img2.write_bytes(img1.read_bytes())  # identical content

    conn = initialize_database(db_root / "faces.db")
    ingest = IngestService(db_root=db_root, conn=conn)

    progress = ingest.start_session([photos], options=IngestOptions(recursive=False))

    assert progress.processed == 1
    assert progress.skipped_existing == 1
    assert progress.total == 2
    count = conn.execute("SELECT COUNT(*) FROM image").fetchone()[0]
    assert count == 1


def test_ingest_rejects_paths_outside_db_root(tmp_path: Path) -> None:
    db_root = tmp_path / "dbroot"
    conn = initialize_database(db_root / "faces.db")
    ingest = IngestService(db_root=db_root, conn=conn)

    outside = tmp_path / "other"
    outside.mkdir()

    try:
        ingest.start_session([outside])
        raise AssertionError("Expected ValueError for out-of-scope folder")
    except ValueError:
        pass


def test_ingest_skips_invalid_detection_boxes(monkeypatch, tmp_path: Path) -> None:
    class DummyDetector:
        def detect_batch(self, images):
            class Det:
                bbox_abs = (1.0, 2.0, 3.0)  # invalid length (missing height)
                bbox_rel = (0.1, 0.1, 0.3)
                confidence = 0.9

            return [[Det()]]

    db_root = tmp_path / "dbroot"
    photos = db_root / "photos"
    img1 = photos / "a.jpg"
    _make_image(img1, (10, 20))

    conn = initialize_database(db_root / "faces.db")
    ingest = IngestService(db_root=db_root, conn=conn)
    monkeypatch.setattr(ingest, "_load_detector", lambda: DummyDetector())

    progress = ingest.start_session([photos], options=IngestOptions(recursive=False))

    assert progress.processed == 1
    assert progress.face_count == 0
    face_rows = conn.execute("SELECT COUNT(*) FROM face").fetchone()[0]
    assert face_rows == 0


def test_ingest_skips_existing_paths_without_hash(monkeypatch, tmp_path: Path) -> None:
    db_root = tmp_path / "dbroot"
    photos = db_root / "photos"
    img1 = photos / "a.jpg"
    _make_image(img1, (10, 10), color="yellow")

    conn = initialize_database(db_root / "faces.db")
    ingest1 = IngestService(db_root=db_root, conn=conn)
    ingest1.start_session([photos], options=IngestOptions(recursive=False))

    # Change file contents to ensure hash would differ; second ingest should still skip by path
    _make_image(img1, (12, 12), color="purple")

    ingest2 = IngestService(db_root=db_root, conn=conn)

    def fake_process(paths, cancel_event=None):
        # Should receive no paths because it is skipped by relative path
        assert not list(paths)
        return iter([])

    monkeypatch.setattr(ingest2, "_process_paths", fake_process)

    progress = ingest2.start_session([photos], options=IngestOptions(recursive=False))

    assert progress.processed == 0
    assert progress.skipped_existing == 1
    count = conn.execute("SELECT COUNT(*) FROM image").fetchone()[0]
    assert count == 1


def test_ingest_supports_cancellation_and_resume(tmp_path: Path) -> None:
    db_root = tmp_path / "dbroot"
    photos = db_root / "photos"
    imgs = [photos / f"img{i}.jpg" for i in range(3)]
    colors = ["red", "green", "blue"]
    for path, color in zip(imgs, colors):
        _make_image(path, (10, 10), color=color)

    conn = initialize_database(db_root / "faces.db")
    ingest = IngestService(db_root=db_root, conn=conn)

    cancel_event = threading.Event()
    last_checkpoint: dict | None = None

    def progress_cb(progress):
        nonlocal last_checkpoint
        last_checkpoint = progress.checkpoint
        if progress.processed >= 1:
            cancel_event.set()

    progress1 = ingest.start_session(
        [photos],
        options=IngestOptions(recursive=True),
        progress_cb=progress_cb,
        cancel_event=cancel_event,
    )

    assert progress1.processed >= 1
    assert progress1.total == 3
    assert last_checkpoint is not None

    progress2 = ingest.start_session(
        [photos],
        options=IngestOptions(recursive=True),
        checkpoint=last_checkpoint,
    )

    assert progress2.cancelled is False
    # Remaining images should be skipped as duplicates or processed, but DB should have all 3
    count = conn.execute("SELECT COUNT(*) FROM image").fetchone()[0]
    assert count == 3


def test_face_crop_expands_by_configured_pct(monkeypatch, tmp_path: Path) -> None:
    class DummyDetector:
        def detect_batch(self, images):
            class Det:
                bbox_abs = (40.0, 40.0, 20.0, 20.0)
                bbox_rel = (0.4, 0.4, 0.2, 0.2)
                confidence = 0.9

            return [[Det()]]

    db_root = tmp_path / "dbroot"
    photos = db_root / "photos"
    img1 = photos / "a.jpg"
    _make_image(img1, (100, 100))

    conn = initialize_database(db_root / "faces.db")
    ingest = IngestService(db_root=db_root, conn=conn, crop_expand_pct=0.1, face_target_size=24)
    monkeypatch.setattr(ingest, "_load_detector", lambda: DummyDetector())

    progress = ingest.start_session([photos], options=IngestOptions(recursive=False))

    assert progress.processed == 1
    row = conn.execute("SELECT face_crop_blob FROM face").fetchone()
    assert row is not None
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(row[0])) as crop:
        assert crop.size == (24, 24)  # 20px expanded by 10% each side -> 24px


def test_face_crops_are_normalized(monkeypatch, tmp_path: Path) -> None:
    class DummyDetector:
        def detect_batch(self, images):
            class Det:
                bbox_abs = (0.0, 0.0, 20.0, 10.0)
                bbox_rel = (0.0, 0.0, 0.2, 0.1)
                confidence = 0.9

            return [[Det()]]

    db_root = tmp_path / "dbroot"
    photos = db_root / "photos"
    img1 = photos / "a.jpg"
    _make_image(img1, (40, 20))

    conn = initialize_database(db_root / "faces.db")
    ingest = IngestService(db_root=db_root, conn=conn, face_target_size=64)
    monkeypatch.setattr(ingest, "_load_detector", lambda: DummyDetector())

    progress = ingest.start_session([photos], options=IngestOptions(recursive=False))

    assert progress.face_count == 1
    row = conn.execute("SELECT face_crop_blob FROM face").fetchone()
    assert row is not None
    with Image.open(BytesIO(row[0])) as crop:
        assert crop.size == (64, 64)


def test_ingest_applies_prediction(monkeypatch, tmp_path: Path) -> None:
    class DummyDetector:
        def detect_batch(self, images):
            class Det:
                bbox_abs = (0.0, 0.0, 10.0, 10.0)
                bbox_rel = (0.0, 0.0, 0.1, 0.1)
                confidence = 0.7

            return [[Det()]]

    class DummyPredictor:
        def predict_batch(self, blobs):
            DummyPredictor.called_with = len(blobs)
            return [{"person_id": 1, "confidence": 0.55} for _ in blobs]

    db_root = tmp_path / "dbroot"
    photos = db_root / "photos"
    img1 = photos / "a.jpg"
    _make_image(img1, (20, 20))

    conn = initialize_database(db_root / "faces.db")
    conn.execute("INSERT INTO person (id, primary_name, first_name, last_name) VALUES (1, 'Test Person', 'Test', 'Person')")
    conn.commit()
    predictor = DummyPredictor()
    ingest = IngestService(db_root=db_root, conn=conn, prediction_service=predictor)
    monkeypatch.setattr(ingest, "_load_detector", lambda: DummyDetector())

    progress = ingest.start_session([photos], options=IngestOptions(recursive=False))

    assert progress.face_count == 1
    assert getattr(DummyPredictor, "called_with", 0) == 1
    row = conn.execute(
        "SELECT predicted_person_id, prediction_confidence FROM face"
    ).fetchone()
    assert row == (1, pytest.approx(0.55))
