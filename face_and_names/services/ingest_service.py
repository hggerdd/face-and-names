"""
Ingest service implementation (detection-free variant).

Responsibilities implemented here:
- Scope enforcement to DB Root (FR-001, FR-002).
- Session tracking and dedupe by content hash (FR-003, FR-007).
- EXIF orientation, metadata extraction, thumbnail generation, and zero-face handling (FR-006, FR-008).

Detection/prediction hooks are intentionally omitted until models are wired.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable, List, Sequence

import imagehash
from PIL import Image

from face_and_names.models.repositories import (
    ImageRepository,
    ImportSessionRepository,
    MetadataRepository,
)
from face_and_names.utils.imaging import extract_metadata, make_thumbnail, normalize_orientation

LOGGER = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass
class IngestOptions:
    recursive: bool = True


@dataclass
class IngestProgress:
    session_id: int
    processed: int
    skipped_existing: int
    errors: list[str]


class IngestService:
    """Ingest images into the database, without detection/prediction."""

    def __init__(self, db_root: Path, conn) -> None:
        self.db_root = db_root
        self.conn = conn
        self.sessions = ImportSessionRepository(conn)
        self.images = ImageRepository(conn)
        self.metadata = MetadataRepository(conn)

    def start_session(
        self, folders: Sequence[str | Path], options: IngestOptions | None = None
    ) -> IngestProgress:
        opts = options or IngestOptions()
        resolved_folders = [self._resolve_folder(folder) for folder in folders]
        self._ensure_scoped_to_root(resolved_folders)

        session_id = self.sessions.create(folder_count=len(resolved_folders), image_count=0)
        processed = 0
        skipped_existing = 0
        errors: List[str] = []

        for image_path in self._iter_images(resolved_folders, recursive=opts.recursive):
            try:
                is_new = self._ingest_one(session_id, image_path)
                if is_new:
                    processed += 1
                    self.sessions.increment_image_count(session_id, delta=1)
                else:
                    skipped_existing += 1
            except Exception as exc:  # pragma: no cover - safety net
                LOGGER.exception("Failed to ingest %s", image_path)
                errors.append(f"{image_path}: {exc}")

        self.conn.commit()
        return IngestProgress(
            session_id=session_id, processed=processed, skipped_existing=skipped_existing, errors=errors
        )

    def _resolve_folder(self, folder: str | Path) -> Path:
        path = Path(folder)
        return path if path.is_absolute() else (self.db_root / path)

    def _ensure_scoped_to_root(self, folders: Iterable[Path]) -> None:
        root = self.db_root.resolve()
        for folder in folders:
            try:
                folder.resolve().relative_to(root)
            except Exception as exc:
                raise ValueError(f"Folder {folder} is outside DB Root {self.db_root}") from exc

    def _iter_images(self, folders: Iterable[Path], recursive: bool) -> Iterable[Path]:
        for folder in folders:
            if recursive:
                iterator = folder.rglob("*")
            else:
                iterator = folder.glob("*")
            for path in iterator:
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    yield path

    def _ingest_one(self, session_id: int, image_path: Path) -> bool:
        # Compute hashes and normalized image bytes
        raw_bytes = image_path.read_bytes()
        normalized = normalize_orientation(raw_bytes)
        content_hash = hashlib.sha256(normalized).digest()
        perceptual_hash, width, height = self._compute_perceptual_hash_and_size(normalized)

        existing_id = self.images.get_by_content_hash(content_hash)
        if existing_id is not None:
            return False

        relative_path = image_path.resolve().relative_to(self.db_root.resolve())
        sub_folder = str(relative_path.parent).replace("\\", "/")
        filename = image_path.name
        has_faces = 0  # detection not wired yet
        import_id = session_id

        thumb_rel_base = Path("cache") / "thumbnails" / str(import_id)
        thumb_dir = self.db_root / thumb_rel_base
        thumb_dir.mkdir(parents=True, exist_ok=True)
        # Insert with temporary thumbnail path; update after writing actual file.
        temp_thumb_path = str(thumb_rel_base / "pending.jpg").replace("\\", "/")

        image_id = self.images.add(
            import_id=import_id,
            relative_path=str(relative_path).replace("\\", "/"),
            sub_folder=sub_folder,
            filename=filename,
            content_hash=content_hash,
            perceptual_hash=perceptual_hash,
            width=width,
            height=height,
            orientation_applied=1,
            has_faces=has_faces,
            thumbnail_path=temp_thumb_path,
            size_bytes=len(raw_bytes),
        )

        final_thumb_rel = str(thumb_rel_base / f"{image_id}.jpg").replace("\\", "/")
        thumb_path = thumb_dir / f"{image_id}.jpg"
        thumb_path.write_bytes(make_thumbnail(normalized, max_width=500))
        self.images.set_thumbnail_path(image_id, final_thumb_rel)

        self.metadata.add_entries(image_id, extract_metadata(raw_bytes), meta_type="EXIF")
        return True

    def _compute_perceptual_hash_and_size(self, image_bytes: bytes) -> tuple[int, int, int]:
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            phash = imagehash.phash(image.convert("RGB"))
            width, height = image.size
        value = int(str(phash), 16)
        if value >= (1 << 63):
            value -= 1 << 64  # store as signed 64-bit integer to fit SQLite
        return value, width, height
