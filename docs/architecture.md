# Face-and-Names v2 – Architecture (current state)

## High-Level
- PyQt desktop shell with background workers to keep UI responsive.
- SQLite holds images/faces/metadata; thumbnails + face crops stored as BLOBs for portability; paths are relative to DB Root.
- Shared person registry (`persons/persons.json`) is the source of truth for Person IDs/names/aliases; each DB mirrors it on open.

## Core Services
- `IngestService`: scope folders, skip already-seen relative paths, hash (SHA-256 + pHash), EXIF/orientation, thumbnails, detection, store crops, optional inline prediction, progress/cancel/resume.
- `PredictionService`: loads model artifacts from `model/` (FaceNet classifier) for batch + inline; handles device fallback.
- `ClusteringService`: DBSCAN/KMeans with feature sources pHash/raw/FaceNet embedding/ArcFace ONNX (falls back to FaceNet if ArcFace missing); writes cluster_ids.
- `PeopleService`: CRUD/merge people + groups backed by registry; cascades merges/renames to faces/groups.
- `FacesWorkspaceController`: Controller for the current Faces workspace. It centralizes folder/image/face queries, workspace mode filters (all/unnamed/predicted/clustered), summary counts, face assignment/deletion, person creation, and original-image lookup so `ui/faces_page.py` can focus on widgets/rendering. The larger unified Faces workspace described in FR-064/FR-067 is being built incrementally.
- `ExportImportService`: **Placeholder (raises `NotImplementedError`).** Portable export/import (FR-055) is planned but not yet functional.
- `DiagnosticsService`: **Placeholder (raises `NotImplementedError`).** Health checks for models/DB/device (FR-048) are planned but not yet functional. Diagnostics is intentionally hidden from the main navigation until a real page exists.

## Data Flow
- Ingest: select folders → create import session → for each file: skip if relative path exists → normalize/orient → hash → metadata → thumbnail → detect faces → save crops → inline predict if model loaded → progress/cancel/checkpoint.
- Clustering: load scoped faces → pick feature source → cluster → renumber/split noise → persist → stats.
- Prediction (batch): load faces (all/unnamed) → predict → update predicted_person_id/confidence → histograms → cancel-safe.
- People: CRUD/merge/group; registry sync keeps IDs stable across DBs; merges rebinding faces/predictions/groups.

## Storage/Config
- Schema lives in `face_and_names/models/schema.sql` with `schema_version`.
- Registry: `persons/persons.json` shared across DB Roots.
- Config/logs live under user config dir + DB Root; offline-first, no outbound calls by default.

## Interfaces (contracts)
- Detector: returns bboxes + confidence; reused per batch.
- Prediction: `predict_batch(faces, options) -> list[person_id, confidence]` with device/threshold handling.
- Model runner: embed or classify; exposes name/version/device/availability.
- Worker jobs: progress metrics, cancel tokens, checkpoints, error list.

## Testing/Resilience
- Unit/integration tests cover ingest skip rules, registry sync, clustering, prediction.
- Background jobs cancellable/resumable; health checks surface missing models and log failures.

## Implementation Status (placeholders)
The first unified Faces workspace slice is implemented in `ui/faces_page.py` through shared mode filters and workspace summary counts. Cluster-specific side panels, prediction histograms, and global start/stop job actions are still planned.

The following components exist as scaffolds only and raise `NotImplementedError`:
- `services/export_import_service.py` — portable export/import (FR-055).
- `services/diagnostics_service.py` — diagnostics/health checks (FR-048); hidden from navigation until implemented.

Legacy artifacts under `face_recognition_models/` (e.g., `face_classifier.joblib`, `face_encoder_complete.pth`, `mtcnn_complete.pth`, `label_encoder.joblib`, `model_config.json`) are **not** used by the current code. The active model artifacts live under `model/` and use `FacenetEmbedder`/`InceptionResnetV1`.
