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
from PIL import Image, ImageOps, ExifTags

from face_and_names.models.repositories import (
    ImageRepository,
    ImportSessionRepository,
    MetadataRepository,
)

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
    total: int
    errors: list[str]
    current_folder: str | None = None
    last_image_name: str | None = None
    last_thumbnail: bytes | None = None


class IngestService:
    """Ingest images into the database, without detection/prediction."""

    def __init__(self, db_root: Path, conn) -> None:
        self.db_root = db_root
        self.conn = conn
        self.sessions = ImportSessionRepository(conn)
        self.images = ImageRepository(conn)
        self.metadata = MetadataRepository(conn)

    def start_session(
        self,
        folders: Sequence[str | Path],
        options: IngestOptions | None = None,
        progress_cb: callable | None = None,
    ) -> IngestProgress:
        opts = options or IngestOptions()
        resolved_folders = [self._resolve_folder(folder) for folder in folders]
        self._ensure_scoped_to_root(resolved_folders)

        session_id = self.sessions.create(folder_count=len(resolved_folders), image_count=0)
        processed = 0
        skipped_existing = 0
        errors: List[str] = []
        images = list(self._iter_images(resolved_folders, recursive=opts.recursive))
        total = len(images)

        LOGGER.info("Ingest session %s started: %d folders, %d images queued", session_id, len(resolved_folders), total)

        for image_path in images:
            try:
                is_new, thumb_bytes = self._ingest_one(session_id, image_path)
                if is_new:
                    processed += 1
                    self.sessions.increment_image_count(session_id, delta=1)
                else:
                    skipped_existing += 1
                    LOGGER.info("Skip duplicate (hash): %s", image_path)
            except Exception as exc:  # pragma: no cover - safety net
                LOGGER.exception("Failed to ingest %s", image_path)
                errors.append(f"{image_path}: {exc}")
            if progress_cb is not None:
                last_image_name = None
                last_thumbnail = None
                if is_new and processed > 0 and processed % 10 == 0:
                    last_image_name = image_path.name
                    last_thumbnail = thumb_bytes
                progress_cb(
                    IngestProgress(
                        session_id=session_id,
                        processed=processed,
                        skipped_existing=skipped_existing,
                        total=total,
                        errors=errors.copy(),
                        current_folder=str(image_path.parent),
                        last_image_name=last_image_name,
                        last_thumbnail=last_thumbnail,
                    )
                )

        self.conn.commit()
        LOGGER.info(
            "Ingest session %s finished: processed=%d skipped=%d errors=%d",
            session_id,
            processed,
            skipped_existing,
            len(errors),
        )
        return IngestProgress(
            session_id=session_id,
            processed=processed,
            skipped_existing=skipped_existing,
            total=total,
            errors=errors,
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

    def _ingest_one(self, session_id: int, image_path: Path) -> tuple[bool, bytes | None]:
        # Compute hashes and normalized image bytes in a single pass
        raw_bytes = image_path.read_bytes()
        normalized_bytes, perceptual_hash, width, height, thumb_bytes, metadata_map = self._process_image(
            raw_bytes
        )
        content_hash = hashlib.sha256(normalized_bytes).digest()

        existing_id = self.images.get_by_content_hash(content_hash)
        if existing_id is not None:
            return False, None

        relative_path = image_path.resolve().relative_to(self.db_root.resolve())
        sub_folder = str(relative_path.parent).replace("\\", "/")
        filename = image_path.name
        has_faces = 0  # detection not wired yet
        import_id = session_id

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
            thumbnail_blob=thumb_bytes,
            size_bytes=len(raw_bytes),
        )

        self.metadata.add_entries(image_id, metadata_map, meta_type="EXIF")
        return True, thumb_bytes

    def _process_image(self, raw_bytes: bytes) -> tuple[bytes, int, int, int, bytes, dict[str, str]]:
        """Return normalized bytes, phash, dimensions, thumbnail bytes, and metadata."""
        with Image.open(BytesIO(raw_bytes)) as image:
            image.load()
            exif_data = image.getexif()
            oriented = ImageOps.exif_transpose(image)
            fmt = oriented.format or "PNG"
            if fmt.upper() in {"JPEG", "JPG"} and oriented.mode not in {"RGB", "L"}:
                oriented = oriented.convert("RGB")

            buffer = BytesIO()
            oriented.save(buffer, format=fmt)
            normalized_bytes = buffer.getvalue()

            phash = imagehash.phash(oriented.convert("RGB"))
            width, height = oriented.size

            thumb = oriented.convert("RGB")
            thumb.thumbnail((500, 500), Image.Resampling.LANCZOS)
            tb = BytesIO()
            thumb.save(tb, format="JPEG", quality=85, optimize=True)
            thumb_bytes = tb.getvalue()

            metadata = self._extract_metadata(exif_data)

        value = int(str(phash), 16)
        if value >= (1 << 63):
            value -= 1 << 64  # store as signed 64-bit integer to fit SQLite
        return normalized_bytes, value, width, height, thumb_bytes, metadata

    def _extract_metadata(self, exif) -> dict[str, str]:
        """Extract EXIF metadata without reopening the image."""
        tag_lookup = ExifTags.TAGS
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
