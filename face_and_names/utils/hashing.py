"""
Hashing utilities scaffold (see docs/hash_scheme.md).
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import imagehash
from PIL import Image

from face_and_names.utils.imaging import normalize_orientation


def compute_content_hash(path: Path) -> bytes:
    """Compute SHA-256 over normalized image bytes (TODO: implement EXIF orientation handling)."""
    normalized = normalize_orientation(path.read_bytes())
    return hashlib.sha256(normalized).digest()


def compute_perceptual_hash(path: Path) -> int:
    """Compute 64-bit pHash on thumbnail-ready image."""
    normalized = normalize_orientation(path.read_bytes())
    with Image.open(BytesIO(normalized)) as image:
        image.load()
        phash = imagehash.phash(image.convert("RGB"))
    return int(str(phash), 16)
