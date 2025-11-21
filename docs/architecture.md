# Face-and-Names v2 – Architecture Outline

This document summarizes the proposed architecture aligned to `docs/requirements.md` and `docs/plan.md`. It is implementation-neutral and non-code.

## High-Level View
- **App shell/UI**: Desktop UI built with PyQt; must remain responsive by using background workers for long tasks (NFR-001/003).
- **Core services** (domain, not infrastructure):
  - `IngestService`: folder selection, session tracking, metadata/EXIF, thumbnails, detection, optional inline prediction, progress/cancel/resume (FR-001..013, FR-051..053).
  - `PredictionService`: single entry for inline and batch; device selection/fallback; pluggable runners (FR-012, FR-034..037, FR-060..063).
  - `DetectorAdapter`: detector interface with padded/clamped bboxes; reusable instance per batch (FR-010/013).
  - `ClusteringService`: algorithms (DBSCAN/KMeans/Hierarchical), post-process split/renumber, stats/progress/cancel (FR-018..022).
  - `FacesWorkspaceController`: unified filters/modes, virtualized grids, face tile interactions, overlays (FR-014..017, FR-064..067).
  - `PeopleService`: people/groups CRUD, merge/rename, alias collisions, group hierarchy (FR-030..033, FR-045..047, FR-068..070).
  - `ExportImportService`: JSON/CSV export/import, conflict handling, relink support (FR-055..057).
  - `DiagnosticsService`: health checks for models/DB/device/cache; repair tools; self-test (FR-048..054, FR-057).
- **Data layer**: SQLite database with tables per conceptual model; thumbnails and face crops stored as BLOBs inside SQLite for portability (FR-072/FR-078); relative paths rooted at DB Root (FR-002).
- **Background workers**: in-process `JobManager` backed by a bounded pool; job metadata for progress (counts/histograms), cancellation tokens, and per-job checkpoints to enable resume (FR-009, FR-052/053). Priority lanes remain a planned enhancement.

## Data Flow (Key Operations)
- **Ingest**: folder selection → session row → for each file in scope: normalize orientation, compute SHA-256 + pHash, skip existing → extract metadata → make thumbnail → detect faces → save bboxes/crops (normalized to configurable square size) → optional inline prediction via `PredictionService` → update progress; failures recorded with retry/skip.
- **Batch prediction**: load faces (all or unnamed) → run prediction in batches → update predicted_person_id/confidence → live histogram/stats → cancel leaves processed rows intact.
- **Clustering**: load scoped faces → run selected algorithm → get cluster labels → post-process (split oversized clusters, renumber, noise handling) → persist cluster_id → stats emitted.
- **Faces workspace**: query faces with filters (scope, confidence range, unnamed-only, differs-from-name, date range, groups) → virtualized grid of face tiles → interactions (toggle select, double-click accept/rename, right-click preview) → updates propagate to DB and UI.
- **People management**: CRUD person/group; merges cascade to faces/images; alias collisions resolved with prompt; group hierarchy implies membership inheritance.
- **Export/import**: serialize people/groups/links and stats; import with dry-run and dedupe via hashes; relink uses relative paths + hashes to match moved files.
- **Diagnostics**: self-test runs sample detection/prediction; checks model presence/version, DB integrity, cache stats; repair tools rebuild thumbnails and surface duplicates.

## Interfaces (Contracts)
- **Detector interface**: `detect(image) -> list[FaceDetection]` where detection includes bbox_abs, bbox_rel, confidence, crop. Supports batch reuse and optional warm-up (FR-010/061).
- **Prediction service API**: `predict_batch(faces, options) -> list[Prediction]` with thresholds, device selection, batch size, warm-up, min face size handling (FR-012, FR-060..062). Caters to inline and batch contexts.
- **Model runner interface**: accepts preprocessed tensor; returns embedding or (person_id, confidence); exposes metadata (name/version/device/default thresholds); indicates availability (FR-063).
- **Worker job contract**: job id, payload, progress metrics (counts/histograms), cancel token, status, resumable checkpoint, error list with retry/skip.
- **Face tile**: displays current name, predicted name+confidence, cluster badge; actions: single-click toggle, double-click accept/rename, right-click preview, delete.

## Concurrency and Resource Use
- Default worker pool small (2–4 CPU, 1 GPU slot); interactive tasks higher priority. Jobs yield periodically; warm-up and batching reduce reload overhead. Configurable caps per device (OI-007, FR-054).

## Storage Strategy
- DB: normalized schema per Data Model (Image, Face, ImportSession, Metadata, Person, Group, PersonGroup, Stats). Indices on hashes, person_id, cluster_id, import_id.
- Media: thumbnails (~<=500px) **and face crops** stored as BLOBs in SQLite (FR-072/FR-078) to keep DB Roots portable; size/quality budgets documented (NFR-012).
- Paths: store relative to DB Root; relink logic uses hashes + relative paths when root moves (FR-002, FR-056).
- Identity: SHA-256 (primary) + 64-bit pHash; collision policy per plan (FR-003, FR-058/059).
- Schema specifics recorded in `docs/schema.md` (numeric bbox columns; normalized aliases); dependencies in `docs/dependencies.md`. Maintain a `schema_version` table and apply forward migrations explicitly instead of re-running the full DDL on startup.
## Configuration
- Global: app settings (device preference, default thresholds, worker caps, logging levels).
- DB-scoped: last folder selections, ingest options, thresholds overrides, UI preferences for that DB Root.
- Storage: human-readable config files (YAML/TOML/JSON) under user config dir and DB Root; no secret storage required by default.

## Logging, Metrics, Audit
- Structured logs with rotation/retention; per-feature surfaces for recent errors (FR-051).
- Metrics: progress for ingest/clustering/prediction, histograms (confidence, cluster sizes), throughput stats.
- Audit log for rename/merge/delete/accept-prediction actions with timestamp and actor (BR-006).

## Observability & Health
- Health checks: model presence/version, DB integrity, cache size, device availability; exposed in diagnostics panel (FR-048/057).
- Self-test: minimal pass/fail run of detection/prediction; clear user feedback.

## Security & Privacy
- Offline by default; no outbound calls without opt-in (NFR-014).
- Optional encryption for DB and media caches; encrypted export option.
- Minimal PII: only names/aliases/birthdates/notes as required; avoid storing more.

## Accessibility & UX Consistency
- Keyboard navigation and shortcuts for face tile actions; focus order and screen reader labels; contrast targets per WCAG 2.1 AA (NFR-013).
- Shared face tile and prediction service used across all views (NFR-005).

## Portability
- DB Root contains DB and image hierarchy; all stored paths relative. Identity hashes enable relink on mount/drive changes and duplicate handling (FR-002, FR-056, NFR-004).

## Testing Strategy (Alignment)
- Requirement-mapped tests (functional + performance + resilience + accessibility).
- Performance probes for startup, ingest throughput, clustering/prediction rates; resource ceilings honored (NFR-010/011/015).
- Resilience tests for cancel/resume and collision handling.
