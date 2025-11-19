# Application Requirements – Target State (rewrite/next-gen)

Single-source specification for the new application. Describes the desired end-state behaviors, UX, data handling, and technical constraints. All flows reference tab names in brackets for clarity, but the UX can be reorganized if needed.

## 1) Scope & Goals
- End-to-end photo workflow: ingest → detect → recognize → cluster → name/verify → browse/annotate → analyze.
- Fast startup and responsive UI on modest hardware; no heavy work before the user invokes a feature.
- Portable, source-scoped datastores so libraries on external drives remain usable regardless of drive letter/mount.
- Consistent UX and shared components/services to avoid duplication.
- Model-agnostic design: face recognition uses person IDs; models are pluggable and do not embed human-readable names.

## 2) Functional Requirements by Flow

### Photo Ingest & Detection (Detection)
- Scope by DB root: only images in the DB folder and its subfolders are ingested; paths stored relative to DB root so drive letters/mount points can change.
- Folder selection with recursive toggle and per-subfolder checkboxes; remember last-used folder in `~/.face_and_names_config.json`.
- Import session tracking: record folder_count and image_count as images are processed; skip files already ingested based on identity (path + hash scheme, below).
- Per image:
  - Correct EXIF orientation; extract EXIF/IPTC metadata.
  - Generate JPEG thumbnail (max width ~500px).
  - Derive relative path triple `(base_folder_rel, sub_folder, filename)`; tolerate flat and nested structures.
  - Compute image identity for dedupe (see Identity section).
- Detection: YOLOv11 with padded, clamped bboxes; save face crops as JPEG; store absolute and relative bboxes; record no-face images but still store thumbnail/metadata.
- Optional inline recognition: call shared prediction service; thresholded predicted person ID + confidence saved with face rows.
- Progress UX: file/folder progress, counts (faces, no-face), indeterminate start, cancelable; detector reused per batch to avoid reloads.

### Photo Browser & Annotation (Thumbnails)
- Tree of folders/images from DB; prev/next navigation; metadata table.
- Show faces overlaid; allow manual drawing of new face boxes with name assignment; mark has_faces accordingly.
- Per-face actions: rename, delete (🗑), hover cues; right-click shows full-image preview with red bbox and labels (name/predicted), using shared preview window.
- Uses thumbnail/detail caches to avoid repeat BLOB fetches.

### Face Grouping (Clustering)
- Load faces filtered by latest import and/or folder selection.
- Choose model (FaceNet variants or future plugins) and algorithm (DBSCAN, KMeans, Hierarchical) with parameter controls.
- Background thread with progress and stats (noise, cluster size distribution); cancelable.
- Persist cluster_id per face; split oversized clusters and renumber sequentially (noise handled explicitly).
- Bulk clear all names and/or cluster assignments.

### Cluster Review & Naming (Naming)
- Grid of clustered faces using the shared face-tile component (image, name, predicted name + confidence, delete, right-click preview).
- Interactions: single-click toggles selection (inactive shown grayscale); double-click image accepts predicted name; double-click name opens rename dialog; delete removes face and refreshes cluster.
- Bulk assign name to selected faces (clears cluster_id); select/deselect all; wrap-around cluster navigation; names list kept in sync; status shows cluster position/count.

### Per-Person Analysis (Name Analysis)
- People list resolved from person IDs: rename person globally (update all faces), manage aliases/short names.
- Selecting a person shows all faces with bboxes; delete per-face; right-click preview; double-click name to rename face.
- Timeline widget: EXIF capture dates for that person; grid auto-calculates columns based on width.

### Batch Recognition (Prediction)
- QThread-based batch inference via shared prediction service; option to process only faces without manual names.
- Writes predicted person ID + confidence; shows confidence histogram and predicted name/ID frequency table; progress/cancel; guards corrupt images.

### Prediction Review (Review Predictions)
- Async data loader to keep UI responsive; filters: name/alias substring, confidence min/max, unnamed only, prediction differs from existing name.
- Virtualized grid of shared face tiles; all selected by default; single-click toggles; double-click accepts prediction; inline rename; right-click preview with bbox.
- Bulk accept predictions for selected faces; filter stats and reload control.

### Data Insights (Database Analysis)
- Stats: total faces, unique files/folders/names, faces with predictions, clusters, images without faces, duplicates across subfolders.
- Clear database action (scoped to this DB) wiping images/faces/thumbnails/metadata with FK-safe ordering and confirmation.

### People Management (new dedicated page)
- CRUD for people (IDs): primary name, aliases/short names, optional birthdate (for age-at-capture calculation), notes.
- Merge people; view linked faces/images; update display names without retraining models.

## 3) Identity & Data

### Image Identity (rename/move resilient)
- Use a robust scheme to detect duplicates and survive renames/moves under the DB root. Recommended hybrid:
  - Relative path from DB root.
  - Content hash (SHA-256) of file bytes OR a perceptual hash for minor edits.
  - Capture dimensions/size as secondary check.
- On ingest, dedupe using identity; allow re-locating library as long as relative layout and identity match.

### Person Identity
- Models and DB store person IDs, not names. Names/aliases resolve at UI time via People records.
- Predictions persist predicted person ID + confidence; accepting/renaming updates the person binding, not the model output.

### Metadata & Thumbnails
- EXIF/IPTC stored as key/type/value per image; replace on re-save.
- Thumbnails and face crops stored as BLOBs; UNIQUE constraint on `(base_folder_rel, sub_folder, filename)`; FK cascades for thumbnails/metadata; indexed lookups.

## 4) Shared Components & Services
- Face tile component: single implementation reused across tabs (image, name, predicted name + confidence, delete, right-click preview).
- Shared preview window: consistent right-click full-image preview with red bbox and labels.
- Shared prediction service: one pipeline (preprocessing, model invocation, thresholding) callable from ingest, batch prediction, and review flows; consistent thresholds/config.
- Background task pattern: standard worker with progress/cancel, UI disable/enable hooks, and auto-refresh callbacks.

## 5) Performance & UX
- Startup: minimal work; health checks (models present, DB writable, device availability) run async where possible; target sub-2s to splash/main on modest hardware.
- Lazy-load heavy models/resources per feature; no tab-specific heavy work until opened.
- UI responsiveness: main thread remains responsive; all long ops show progress and are cancelable.
- Consistent style guide: typography, spacing, buttons, panels; informative labels/tooltips (e.g., “Face recognition confidence”).
- Accessibility/lightweight theming as stretch goal; avoid flashy UI but keep it polished.

## 6) Model & Plugin Strategy
- Pluggable model runner interface: metadata (name, version, device), input/output contract (embedding/vector, labels as person IDs), configurable thresholds.
- Support multiple recognizers in future without UI rewrites; model selection persisted and validated.
- Training workflow TBD; models should not embed user-visible names—mapping handled via People records.

## 7) State & Views
- Face state transitions: unknown → predicted → confirmed (manual or accepted prediction); provenance retained.
- Views focus on: recent import/cluster view, prediction-focused review, person-focused analysis.

## 8) Reliability & Diagnostics
- Clear errors for missing models or corrupt images; skip/retry strategy with logging.
- Diagnostics panel: model presence, DB health, cache stats, device selection (CPU/GPU).
- Ensure thumbnails exist even when no faces found; fixer tools for missing thumbnails/duplicates.
