"""
Hashing utilities scaffold (see docs/hash_scheme.md).
"""

from __future__ import annotations

from pathlib import Path


def compute_content_hash(path: Path) -> bytes:
    """Compute SHA-256 over normalized image bytes (TODO: implement EXIF orientation handling)."""
    raise NotImplementedError


def compute_perceptual_hash(path: Path) -> int:
    """Compute 64-bit pHash on thumbnail-ready image."""
    raise NotImplementedError
