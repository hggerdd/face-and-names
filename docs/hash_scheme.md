# Face-and-Names v2 – Identity/Hash Scheme Details

## Purpose
- Prevent duplicate ingest of the same image content even if renamed/moved (FR-003, FR-058/059, BR-004).
- Relink when DB Root moves while preserving relative structure (NFR-004).
- Surface near-duplicates for user review (FR-050).

## Hashes
- **Content hash (primary)**: SHA-256 over normalized image bytes *after* EXIF orientation correction, *before* resizing or thumbnailing.
- **Perceptual hash (secondary)**: 64-bit pHash computed on the thumbnail-ready image (≈500px width JPEG).

## Storage
- `image.content_hash`: BLOB (32 bytes).
- `image.perceptual_hash`: INTEGER (unsigned 64-bit).
- Index on `perceptual_hash` for distance queries; unique constraint on `content_hash`.

## Collision / Conflict Handling
- **Exact match (SHA-256 equal)**:
  - If path differs → treat as move/rename; update relative_path/sub_folder/filename; log event.
  - If already present with same path → skip ingest.
- **Near-duplicate (pHash within threshold, SHA-256 different)**:
  - Flag for duplicate workflow; keep both; let user choose keep/replace/mark duplicate; log decision.
- **Hash collision (same SHA-256 with differing metadata/dimensions)**:
  - Treat as conflict; keep original, log error, require user decision before overwrite.

## Thresholds
- pHash distance threshold configurable (default small, e.g., ≤5) for near-duplicate surfacing.
- Minimum face size threshold enforced during detection; skipped faces recorded with reason (FR-062).

## Relink Strategy
- On DB Root change: scan new root for files; match by `content_hash`; update relative paths. If not found, use pHash + filename/subfolder hints; mark unresolved items and log.

## Audit/Logging
- Moves/renames, duplicate decisions, and conflicts are logged with timestamps; linked to audit log when user choice required.
