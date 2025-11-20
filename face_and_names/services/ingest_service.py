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
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple

import imagehash
from PIL import Image, ImageOps, ExifTags

from face_and_names.models.repositories import (
    FaceRepository,
    ImageRepository,
    ImportSessionRepository,
    MetadataRepository,
)
from face_and_names.services.detector_adapter import DetectorAdapter, FaceDetection  # type: ignore

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
    last_face_thumbs: list[bytes] | None = None


class IngestService:
    """Ingest images into the database, without detection/prediction."""

    def __init__(self, db_root: Path, conn) -> None:
        self.db_root = db_root
        self.conn = conn
        self.sessions = ImportSessionRepository(conn)
        self.images = ImageRepository(conn)
        self.metadata = MetadataRepository(conn)
        self.faces = FaceRepository(conn)
        self.processing_workers = max(2, min(8, (os.cpu_count() or 4)))

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
        paths = list(self._iter_images(resolved_folders, recursive=opts.recursive))
        total = len(paths)

        LOGGER.info("Ingest session %s started: %d folders, %d images queued", session_id, len(resolved_folders), total)

        detector = self._load_detector()
        self._ensure_face_crop_column()

        for result in self._process_paths(paths):
            image_path = result.path
            is_new = False
            thumb_bytes = None
            face_thumbs = None
            try:
                if result.error:
                    raise result.error
                is_new, thumb_bytes, face_thumbs = self._ingest_one(
                    session_id, image_path, result.raw_bytes, result, detector
                )
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
                last_faces = None
                if is_new and (processed == 1 or processed % 10 == 0):
                    last_image_name = image_path.name
                    last_thumbnail = thumb_bytes
                    last_faces = face_thumbs
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
                        last_face_thumbs=last_faces,
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

    def _ingest_one(
        self,
        session_id: int,
        image_path: Path,
        raw_bytes: bytes,
        processed: "ProcessedImage",
        detector: DetectorAdapter | None,
    ) -> tuple[bool, bytes | None, list[bytes] | None]:
        # Hashes already computed in worker; reuse
        normalized_bytes = processed.normalized_bytes
        perceptual_hash = processed.perceptual_hash
        width = processed.width
        height = processed.height
        thumb_bytes = processed.thumb_bytes
        metadata_map = processed.metadata
        content_hash = hashlib.sha256(normalized_bytes).digest()

        existing_id = self.images.get_by_content_hash(content_hash)
        if existing_id is not None:
            return False, None, None

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

        face_preview: list[bytes] | None = None
        if detector is not None:
            faces = self._detect_faces(detector, normalized_bytes, width, height)
            face_preview = self._persist_faces(faces, image_id, import_id, normalized_bytes, image_path)

        return True, thumb_bytes, face_preview

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

    def _process_paths(self, paths: Sequence[Path]) -> Iterable["ProcessedImage"]:
        """Process images in parallel (IO + CPU) then yield results for DB writes (FR-076/FR-077)."""
        with ThreadPoolExecutor(max_workers=self.processing_workers) as executor:
            for result in executor.map(self._process_single_path, paths):
                yield result

    def _ensure_face_crop_column(self) -> None:
        """Add face_crop_blob column if missing (migration helper)."""
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(face)")}.copy()
        if "face_crop_blob" not in cols:
            LOGGER.warning("Adding missing face_crop_blob column to face table")
            self.conn.execute("ALTER TABLE face ADD COLUMN face_crop_blob BLOB NOT NULL DEFAULT x'';")
            self.conn.commit()

    def _load_detector(self) -> DetectorAdapter | None:
        weights = Path(__file__).resolve().parents[2] / "yolov11n-face.pt"
        if not weights.exists():
            LOGGER.warning("Detector weights not found at %s; skipping detection", weights)
            return None
        try:
            detector = DetectorAdapter(weights_path=weights)
            detector.load()
            LOGGER.info("Loaded detector from %s", weights)
            return detector
        except Exception as exc:  # pragma: no cover
            LOGGER.error("Failed to load detector: %s", exc)
            return None

    def _detect_faces(
        self, detector: DetectorAdapter, normalized_bytes: bytes, width: int, height: int
    ) -> list[FaceDetection]:
        try:
            with Image.open(BytesIO(normalized_bytes)) as image:
                image.load()
                detections = detector.detect_batch([image])[0]
            return detections
        except Exception as exc:  # pragma: no cover
            LOGGER.error("Detection failed: %s", exc)
            return []

    def _persist_faces(
        self,
        detections: list[FaceDetection],
        image_id: int,
        import_id: int,
        normalized_bytes: bytes,
        image_path: Path,
    ) -> list[bytes]:
        preview: list[bytes] = []
        if not detections:
            return preview
        with Image.open(BytesIO(normalized_bytes)) as image:
            image.load()
            for idx, det in enumerate(detections):
                x, y, w, h = det.bbox_abs
                crop = image.crop((x, y, x + w, y + h))
                buf = BytesIO()
                crop.convert("RGB").save(buf, format="JPEG", quality=85, optimize=True)
                crop_bytes = buf.getvalue()
                self.faces.add(
                    image_id=image_id,
                    bbox_abs=det.bbox_abs,
                    bbox_rel=det.bbox_rel,
                    face_crop_blob=crop_bytes,
                    cluster_id=None,
                    person_id=None,
                    predicted_person_id=None,
                    prediction_confidence=det.confidence,
                    provenance="detected",
                )
                if idx < 5:
                    preview.append(crop_bytes)
        return preview

    def _process_single_path(self, path: Path) -> "ProcessedImage":
        try:
            raw_bytes = path.read_bytes()
            normalized_bytes, phash, width, height, thumb_bytes, metadata = self._process_image(raw_bytes)
            return ProcessedImage(
                path=path,
                raw_bytes=raw_bytes,
                normalized_bytes=normalized_bytes,
                perceptual_hash=phash,
                width=width,
                height=height,
                thumb_bytes=thumb_bytes,
                metadata=metadata,
                error=None,
            )
        except Exception as exc:
            return ProcessedImage(
                path=path,
                raw_bytes=b"",
                normalized_bytes=b"",
                perceptual_hash=0,
                width=0,
                height=0,
                thumb_bytes=b"",
                metadata={},
                error=exc,
            )


@dataclass
class ProcessedImage:
    path: Path
    raw_bytes: bytes
    normalized_bytes: bytes
    perceptual_hash: int
    width: int
    height: int
    thumb_bytes: bytes
    metadata: dict[str, str]
    error: Exception | None
