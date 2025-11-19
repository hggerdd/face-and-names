from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from face_and_names.utils.hashing import compute_content_hash, compute_perceptual_hash
from face_and_names.utils.imaging import extract_metadata, make_thumbnail, normalize_orientation


def _make_image_bytes(size: tuple[int, int], orientation: int | None = None) -> bytes:
    image = Image.new("RGB", size, color="red")
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    return buffer.getvalue()


def test_normalize_orientation_applies_exif_rotation(tmp_path: Path) -> None:
    image_bytes = _make_image_bytes((10, 20), orientation=6)
    normalized = normalize_orientation(image_bytes)

    with Image.open(BytesIO(normalized)) as oriented:
        assert oriented.size == (20, 10)


def test_extract_metadata_reads_exif() -> None:
    image_bytes = _make_image_bytes((8, 8), orientation=3)

    metadata = extract_metadata(image_bytes)

    assert metadata.get("Orientation") == "3"


def test_thumbnail_respects_max_dimension(tmp_path: Path) -> None:
    image_bytes = _make_image_bytes((1200, 600))
    thumbnail_bytes = make_thumbnail(image_bytes, max_width=200)

    with Image.open(BytesIO(thumbnail_bytes)) as thumb:
        width, height = thumb.size
        assert max(width, height) <= 200
        assert thumb.format == "JPEG"


def test_hashes_ignore_exif_orientation(tmp_path: Path) -> None:
    portrait_path = tmp_path / "portrait.jpg"
    landscape_path = tmp_path / "landscape.jpg"

    portrait_path.write_bytes(_make_image_bytes((10, 20), orientation=6))
    landscape_image = Image.new("RGB", (20, 10), color="red")
    landscape_image.save(landscape_path)

    content_hash_with_exif = compute_content_hash(portrait_path)
    content_hash_rotated = compute_content_hash(landscape_path)
    perceptual_with_exif = compute_perceptual_hash(portrait_path)
    perceptual_rotated = compute_perceptual_hash(landscape_path)

    assert content_hash_with_exif == content_hash_rotated
    assert perceptual_with_exif == perceptual_rotated
