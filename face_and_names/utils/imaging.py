"""
Imaging utilities scaffold: EXIF orientation, thumbnailing, metadata extraction.
"""

from __future__ import annotations


def normalize_orientation(image_bytes: bytes) -> bytes:
    """Apply EXIF orientation; return normalized bytes."""
    raise NotImplementedError


def extract_metadata(image_bytes: bytes) -> dict[str, str]:
    """Extract EXIF/IPTC metadata."""
    raise NotImplementedError


def make_thumbnail(image_bytes: bytes, max_width: int = 500) -> bytes:
    """Produce thumbnail bytes."""
    raise NotImplementedError
