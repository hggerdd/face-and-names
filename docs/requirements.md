# Requirements (rewrite/next-gen)

Single-source reference for the reboot. Derived from the v1.0.0 behavior and captured needs; use this to lock scope before redesigning the schema and UI.

## Functional Flows (tab names in brackets)

### Photo Ingest & Face Detection (Detection)
- Select base folder; optional recursive scan; tree with per-subfolder checkboxes; remember last folder in `~/.face_and_names_config.json`.
- Start import session (records folder_count, image_count as images are processed); skip files already ingested via `(base_folder, sub_folder, filename)`.
- Per image: correct EXIF orientation, extract EXIF/IPTC metadata, create JPEG thumbnail (max width 500), store path triple with optional base_root for flat/nested folders.
- Run YOLOv11 detector with padded boxes; save face crops (JPEG), absolute and relative bboxes; record no-face images and still keep thumbnail/metadata.
- Optional inline recognition if models exist: FaceNet encoder + sklearn classifier; thresholded predicted_name + confidence stored with face rows.
- Progress UX: file/folder progress, counts (faces, no-face), indeterminate start, cancel support; detector reused per folder to avoid reloads.
- Performance: heavy imports guarded; minimal startup load; lazy model init.

### Photo Browser & Annotation (Thumbnails)
- Folder/image tree from DB; prev/next navigation; metadata table.
- Display face boxes; allow manual drawing to add annotations (bbox + name) and mark has_faces.
- Per-face actions: rename, delete (🗑 button), hover cues.
- Right-click preview with bbox overlay; shared preview window; closes on release. Uses thumbnail/detail caches to avoid repeat BLOB fetches.

### Face Grouping (Clustering)
- Load faces (latest import only toggle; folder filter via tree selection).
- Choose model (FaceNet variants) and algorithm (DBSCAN, KMeans, Hierarchical) with parameter widgets and sensible defaults.
- Background thread with progress + stats (noise points, cluster size distribution); cancelable.
- Persist cluster_id per face; post-process oversized clusters (split) and renumber sequentially (noise handled).
- Bulk clear all names; clear cluster assignments when needed.

### Cluster Review & Naming (Naming)
- Grid of clustered faces showing current name and predicted name/confidence.
- Interactions: single-click toggles selection (inactive shown grayscale); double-click image accepts predicted name; double-click name opens rename dialog; delete button removes face from DB and refreshes cluster.
- Bulk assign name to selected faces (clears cluster_id); select/deselect all; navigate clusters with wrap-around; names list sidebar stays updated; status shows cluster position/count.

### Per-Person Analysis (Name Analysis)
- List of unique names; rename a person globally (update all faces).
- Selecting a name loads all faces with bboxes; delete per-face; right-click preview; double-click name to rename face.
- Timeline widget shows EXIF dates for selected name.
- Grid auto-calculates columns based on width.

### Model Training (VGGFace, legacy)
- UI stub; ModelManager loads checkpoints (ResNet18/50, FaceNet, VGG) handling state_dict vs full modules, class mappings, and accuracy.

### Batch Recognition (Prediction)
- QThread-based batch inference; option to process only faces without manual names.
- Shared preprocessing; writes predicted_name + confidence; histogram of confidences and predicted name frequency table; progress/cancel UX; guards for corrupt images.

### Prediction Review (Review Predictions)
- Async data loader to avoid UI freeze; filters: name substring, confidence min/max, unnamed only, prediction differs from existing name.
- Grid virtualized to render visible items; all faces selected by default; single-click toggles selection; double-click accepts predicted name; inline rename; right-click preview with bbox.
- Bulk accept predictions for selected faces; filter stats and reload control.

### Data Insights (Database Analysis)
- Stats: total faces, unique files/folders/names, faces with predictions, clusters, images without faces, duplicates across subfolders.
- Clear database action (in Detection tab) wiping images/faces/thumbnails/metadata with FK-safe ordering.

## Pipeline & Data Handling
- Image load with EXIF-based rotation; OpenCV BGR pipeline.
- Detector padding applied and clamped to bounds.
- Shared preprocessing: BGR→RGB, resize 160×160, normalize `(x-127.5)/128`, tensor CHW float32.
- Metadata: EXIF/IPTC extraction stored as keyed rows per image; replaces existing on re-save.
- Thumbnails/face bytes stored in DB; UNIQUE constraint on `(base_folder, sub_folder, filename)`; FK cascades for thumbnails/metadata; indexed lookups.
- Caching: LRU caches for thumbnails and image details; async thumbnail/prediction review loaders to keep UI responsive.
- Platform helpers for opening files/folders per OS.

## Backlog / Additional Requirements
- Faster startup: early model/weights check; parallelize safe init; keep heavy imports lazy; no heavy tab-specific work until the tab is opened.
- Better filtering/search: date/month filters (mentioned “circles” UI), person combinations (A & B not C) with indexed queries and UI surfacing.
- Reliability: clear errors when models missing; GPU/CPU selection guard; skip/retry corrupt images; ensure thumbnails even when no faces.
- Consistent UX patterns: standardized progress/cancel, disabled controls during work, harmonized double-click semantics for accepting predictions; richer tooltips/labels (e.g., “Face recognition confidence” vs “confidence”).
- Import robustness: resumable imports; dedupe handling; diagnostics panel for health checks (models present, DB writable, CUDA availability).
- Data quality tools: duplicate filename review UI; fixer for missing thumbnails; low-confidence prediction review flow.
- Clustering enhancements: persist parameters per run; rerun on subsets; noise/outlier review UI.
- Naming workflow: batch-accept predictions above threshold; keyboard shortcuts; wrap behavior defined.
- Prediction review: focus filters for low confidence; batch accept/reject flows.
- Nice-to-have: export/import of data with thumbnails; optional telemetry (opt-in); accessibility/theming.

## Next Iteration Checklist
- Finalize user stories with success/error cases per flow (import, clustering, naming, prediction, browsing).
- Set performance budgets: startup target, ingest throughput (with/without inline recognition), max UI stall; pick a background task pattern (queue/workers, progress/cancel contract, auto-refresh hooks).
- Lock interaction rules: click vs double-click, delete semantics (confirm/undo?), preview behavior (hold vs toggle), batch accept rules.
- After requirements lock: design schema (images/faces/metadata/clusters/predictions with versioning), model artifact contracts/validation, caching/eviction policy.
- Technical decisions: stack (likely PyQt + SQLite), module boundaries to avoid heavy startup imports, testing approach (headless with stubs; regression smokes).
- Risks/open questions: expected dataset scale, in-app vs external training and model delivery, resumable import strategy, duplicate handling policy.

## New/Expanded Requirements from v1 Experience

### Source-Scoped Datastores
- DB file defines the root scope: only images inside the DB’s folder and its subfolders are eligible (e.g., `X:/Bilder/image-and-face.db` scopes to `X:/Bilder/**`).
- Paths must be drive-agnostic/portable: store paths relative to the DB root; tolerate drive letter changes and different mount points.
- To analyze a new library, create a new DB in the corresponding root folder; switching drives should not break lookups as long as relative paths persist.

### Identity and People Management
- Internal models operate on stable person IDs, not names. Names/aliases are user-facing bindings on top of IDs.
- People entity: primary name, short name/aliases, optional metadata (notes), optional birthdate to compute age at capture date (fun but non-mandatory).
- People management page: create/edit/merge people, manage aliases, view linked faces/images, change display name without retraining models.
- Predictions store predicted person IDs; user-visible names resolved via people records; updates to names should not require model retrain.

### Image Identity (beyond filename)
- Add robust image identity to survive renames/moves; proposed options (choose and document one or a hybrid):
  1) Per-file content hash (e.g., SHA-256 of bytes or downscaled hash) + size as primary key.
  2) Perceptual hash (pHash/aHash) to survive minor edits/resaves.
  3) EXIF capture timestamp + pixel hash fallback when hash unavailable.
  4) Relative path (to DB root) + inode/mtime fingerprint as a cheap fast check plus hash confirmation.
  5) Stored thumbnail hash to detect duplicate content on re-import.
- Requirement: dedupe guard on ingest using chosen identity scheme; allow re-locating library as long as relative layout is preserved.

### UI/UX Cohesion
- Single style guide across tabs: consistent typography, spacing, buttons, cards/panels. Not fancy, but polished and readable.
- Tooltips and labels must be informative (e.g., “Face recognition confidence”); onboarding hints where workflows are complex.
- Consolidated navigation: clarify which “pages” are needed (e.g., ingest, cluster, name, prediction review, insights) and reduce redundancy between similar prediction/naming views.
- Progress everywhere long actions happen; no expensive work before a tab is opened.

### Performance-First Design
- Lazy-load models/resources per feature; preload health checks asynchronously.
- Background workers for long tasks with progress/cancel; keep main thread responsive on modest hardware.
- Define acceptable latency budgets and measure (startup, per-image ingest, tab switching, cluster/prediction throughput).

### States and Views for Faces
- Track face states by person ID and provenance (manual vs predicted) but surface a simple set of views:
  - Recent import grouping/cluster view.
  - Prediction-focused view (group by predicted ID, confidence filters).
  - Name-focused view (per-person list with timeline/metadata).
- Ensure state transitions are clear: unknown → predicted → confirmed (manual or accepted prediction), but models stay ID-based.

### Future Model Plug-in
- Architecture should allow adding new recognition models/providers (local or external) without UI rewrites: defined interface for model runners, metadata (name, version, device), input/output contracts (embedding size, label type).
- Model selection/configurable thresholds per model; validation/health checks at startup and per-run.
