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
import threading
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
    face_count: int
    no_face_images: int
    errors: list[str]
    current_folder: str | None = None
    last_image_name: str | None = None
    last_thumbnail: bytes | None = None
    last_face_thumbs: list[bytes] | None = None
    cancelled: bool = False
    checkpoint: dict[str, object] | None = None


class IngestService:
    """Ingest images into the database, without detection/prediction."""

    def __init__(self, db_root: Path, conn, crop_expand_pct: float = 0.05, face_target_size: int = 224) -> None:
        self.db_root = db_root
        self.conn = conn
        self.sessions = ImportSessionRepository(conn)
        self.images = ImageRepository(conn)
        self.metadata = MetadataRepository(conn)
        self.faces = FaceRepository(conn)
        self.processing_workers = max(2, min(8, (os.cpu_count() or 4)))
        self.crop_expand_pct = crop_expand_pct
        self.face_target_size = max(1, int(face_target_size))

    def start_session(
        self,
        folders: Sequence[str | Path],
        options: IngestOptions | None = None,
        progress_cb: callable | None = None,
        cancel_event: threading.Event | None = None,
        checkpoint: dict[str, object] | None = None,
    ) -> IngestProgress:
        opts = options or IngestOptions()
        resolved_folders = [self._resolve_folder(folder) for folder in folders]
        self._ensure_scoped_to_root(resolved_folders)

        session_id = self.sessions.create(folder_count=len(resolved_folders), image_count=0)
        processed = 0
        skipped_existing = 0
        face_count = 0
        no_face_images = 0
        errors: List[str] = []
        paths_all = list(self._iter_images(resolved_folders, recursive=opts.recursive))
        start_index = int(checkpoint.get("next_index", 0)) if checkpoint else 0
        paths = paths_all[start_index:]
        total = len(paths)
        cancelled = False
        checkpoint_payload: dict[str, object] | None = {"next_index": start_index}

        LOGGER.info("Ingest session %s started: %d folders, %d images queued", session_id, len(resolved_folders), total)

        detector = self._load_detector()
        self._ensure_face_crop_column()

        for idx, result in enumerate(self._process_paths(paths, cancel_event=cancel_event), start=start_index):
            image_path = result.path
            is_new = False
            thumb_bytes = None
            face_thumbs = None
            checkpoint_payload = {"next_index": idx + 1}
            try:
                if cancel_event and cancel_event.is_set():
                    cancelled = True
                    break
                if result.error:
                    raise result.error
                is_new, thumb_bytes, face_thumbs, faces_added = self._ingest_one(
                    session_id, image_path, result.raw_bytes, result, detector
                )
                if is_new:
                    processed += 1
                    self.sessions.increment_image_count(session_id, delta=1)
                    if detector is not None:
                        face_count += faces_added
                        if faces_added == 0:
                            no_face_images += 1
                else:
                    skipped_existing += 1
                    LOGGER.info("Skip duplicate (hash): %s", image_path)
            except Exception as exc:  # pragma: no cover - safety net
                LOGGER.exception("Failed to ingest %s", image_path)
                errors.append(f"{image_path}: {exc}")
            if (processed + skipped_existing) % 10 == 0:
                self.conn.commit()
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
                        face_count=face_count,
                        no_face_images=no_face_images,
                        cancelled=cancelled,
                        checkpoint=checkpoint_payload,
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
            face_count=face_count,
            no_face_images=no_face_images,
            cancelled=cancelled,
            checkpoint=checkpoint_payload if total else None,
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
    ) -> tuple[bool, bytes | None, list[bytes] | None, int]:
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
            return False, None, None, 0

        relative_path = image_path.resolve().relative_to(self.db_root.resolve())
        sub_folder = str(relative_path.parent).replace("\\", "/")
        filename = image_path.name
        has_faces = 0
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
        faces_added = 0
        if detector is not None:
            faces = self._detect_faces(detector, normalized_bytes, width, height)
            face_preview, stored_faces = self._persist_faces(
                faces, image_id, import_id, normalized_bytes, image_path
            )
            faces_added = stored_faces
            has_faces = 1 if faces_added else 0

        # Update has_faces once detection is known
        self.conn.execute("UPDATE image SET has_faces = ? WHERE id = ?", (has_faces, image_id))

        return True, thumb_bytes, face_preview, faces_added

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

    def _process_paths(
        self, paths: Sequence[Path], cancel_event: threading.Event | None = None
    ) -> Iterable["ProcessedImage"]:
        """Process images in parallel (IO + CPU) then yield results for DB writes (FR-076/FR-077)."""
        with ThreadPoolExecutor(max_workers=self.processing_workers) as executor:
            for result in executor.map(self._process_single_path, paths):
                yield result
                if cancel_event is not None and cancel_event.is_set():
                    break

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

    def _expand_bbox(
        self, bbox_abs: Sequence[float], img_w: float, img_h: float, expand_pct: float
    ) -> tuple[float, float, float, float]:
        """Expand bbox by pct on all sides, clamped to image bounds."""
        x, y, w, h = bbox_abs
        cx = x + w / 2.0
        cy = y + h / 2.0
        new_w = w * (1 + 2 * expand_pct)
        new_h = h * (1 + 2 * expand_pct)
        new_x1 = max(0.0, cx - new_w / 2.0)
        new_y1 = max(0.0, cy - new_h / 2.0)
        new_x2 = min(img_w, cx + new_w / 2.0)
        new_y2 = min(img_h, cy + new_h / 2.0)
        return new_x1, new_y1, max(0.0, new_x2 - new_x1), max(0.0, new_y2 - new_y1)

    def _persist_faces(
        self,
        detections: list[FaceDetection],
        image_id: int,
        import_id: int,
        normalized_bytes: bytes,
        image_path: Path,
    ) -> tuple[list[bytes], int]:
        preview: list[bytes] = []
        stored = 0
        if not detections:
            return preview, stored
        with Image.open(BytesIO(normalized_bytes)) as image:
            image.load()
            img_w, img_h = image.size
            for idx, det in enumerate(detections):
                if len(det.bbox_abs) != 4 or len(det.bbox_rel) != 4:
                    LOGGER.warning("Skipping invalid detection bbox for %s: %s", image_path, det.bbox_abs)
                    continue
                x, y, w, h = self._expand_bbox(det.bbox_abs, img_w, img_h, self.crop_expand_pct)
                crop = image.crop((x, y, x + w, y + h))
                crop_bytes = self._normalize_crop(crop, target_size=self.face_target_size)
                self.faces.add(
                    image_id=image_id,
                    bbox_abs=det.bbox_abs,
                    bbox_rel=det.bbox_rel,
                    face_crop_blob=crop_bytes,
                    face_detection_index=det.confidence,
                    cluster_id=None,
                    person_id=None,
                    predicted_person_id=None,
                    prediction_confidence=None,
                    provenance="detected",
                )
                stored += 1
                if idx < 5:
                    preview.append(crop_bytes)
        return preview, stored

    def _normalize_crop(self, crop: Image.Image, target_size: int) -> bytes:
        """Resize crop to target square with padding to preserve aspect ratio."""
        ts = max(1, int(target_size))
        bg = Image.new("RGB", (ts, ts), color="white")
        w, h = crop.size
        scale = min(ts / w, ts / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        resized = crop.resize((new_w, new_h), Image.Resampling.LANCZOS)
        x_off = (ts - new_w) // 2
        y_off = (ts - new_h) // 2
        bg.paste(resized, (x_off, y_off))
        buf = BytesIO()
        bg.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()

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
