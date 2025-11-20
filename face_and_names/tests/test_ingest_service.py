from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFile

from face_and_names.models.db import initialize_database
from face_and_names.services.ingest_service import IngestOptions, IngestService

ImageFile.LOAD_TRUNCATED_IMAGES = True


def _make_image(path: Path, size: tuple[int, int], orientation: int | None = None) -> None:
    image = Image.new("RGB", size, color="red")
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
