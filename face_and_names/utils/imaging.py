"""
Imaging utilities scaffold: EXIF orientation, thumbnailing, metadata extraction.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any, Mapping

from PIL import Image, ImageOps, ExifTags

def normalize_orientation(image_bytes: bytes) -> bytes:
    """Apply EXIF orientation; return normalized bytes."""
    with Image.open(BytesIO(image_bytes)) as image:
        image.load()
        oriented = ImageOps.exif_transpose(image)
        fmt = oriented.format or "PNG"
        if fmt.upper() in {"JPEG", "JPG"} and oriented.mode not in {"RGB", "L"}:
            oriented = oriented.convert("RGB")
        buffer = BytesIO()
        oriented.save(buffer, format=fmt)
    return buffer.getvalue()


def extract_metadata(image_bytes: bytes) -> dict[str, str]:
    """Extract EXIF/IPTC metadata."""
    with Image.open(BytesIO(image_bytes)) as image:
        image.load()
        exif = image.getexif()
    tag_lookup: Mapping[int, str] = ExifTags.TAGS
    metadata: dict[str, str] = {}
    for tag_id, value in exif.items():
        tag_name = tag_lookup.get(tag_id, str(tag_id))
        if isinstance(value, bytes):
            try:
                metadata[tag_name] = value.decode(errors="ignore")
            except Exception:
                metadata[tag_name] = repr(value)
        else:
            metadata[tag_name] = str(value)
    return metadata


def make_thumbnail(image_bytes: bytes, max_width: int = 500) -> bytes:
    """Produce thumbnail bytes."""
    with Image.open(BytesIO(image_bytes)) as image:
        image.load()
        oriented = ImageOps.exif_transpose(image)
        thumb = oriented.convert("RGB")
        thumb.thumbnail((max_width, max_width), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        thumb.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()
