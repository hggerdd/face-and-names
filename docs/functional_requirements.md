# Functional Requirements

This captures the current feature set organized by the main UI tabs/flows. Use it as a baseline spec for a restart.

## Photo Ingest & Face Detection (Detection tab)
- Folder selection: remembers last-used folder in `~/.face_and_names_config.json`; supports recursive scan toggle; displays tree with checkboxes per subfolder.
- Import bookkeeping: start import session (folder_count) and update image_count per processed image.
- Image ingest: correct EXIF orientation, extract EXIF/IPTC metadata, generate thumbnails, derive `(base_folder, sub_folder, filename)` using optional base_root to support flat or nested inputs; skip if already processed.
- Face detection: YOLOv11 with padding; captures absolute and relative bboxes; saves cropped faces as JPEG; supports “no faces” recording.
- Inline prediction: optional; loads FaceNet encoder + sklearn classifier if models exist; applies threshold; attaches predicted_name + confidence to face rows.
- Metadata persistence: replace metadata per image; foreign keys and cascading deletes for thumbnails/metadata.
- Progress UX: per-file and per-folder signals, counts of faces/no-face images, indeterminate progress at start, cancelability.
- Performance: lazy-create detector per folder; avoid reloading heavy models unless needed; guard heavy imports behind TYPE_CHECKING elsewhere.

## Photo Browser & Annotation (Thumbnails tab)
- Folder/image tree built from DB; selecting node loads thumbnails and metadata; prev/next navigation.
- Shows face boxes and allows manual drawing to add annotations (bbox + name) and mark has_faces.
- Context interactions on face overlays: rename, delete (🗑) button per face, hover cues.
- Right-click preview with bbox overlay; shared preview window; closes on mouse release; uses cached thumbnails and image detail cache to minimize DB hits.
- Handles duplicates and missing data gracefully (warnings, safe fallbacks).

## Face Grouping (Clustering tab)
- Loads faces (optionally latest import only; optional folder filter from tree widget); caches selection state.
- Model selection: FaceNet variants (VGGFace2 / CASIA); clustering algorithms DBSCAN/KMeans/Hierarchical with parameter widgets and defaults.
- Background thread with progress messages and stats (noise points, cluster size distribution); cancel support.
- Saves cluster_id for each face; post-process to split oversized clusters and renumber sequentially (noise as -1→0 mapping).
- Bulk clear all names; updates UI labels accordingly.

## Cluster Review & Naming (Naming tab)
- Loads clusters ordered; shows grid of faces with current name and predicted name/confidence chips.
- Interactions:
  - Single-click toggles selection (active/inactive grayscale).
  - Double-click image accepts predicted name (calls DB update, refreshes clusters).
  - Double-click name opens rename dialog for that face.
  - Delete button per face removes it from DB and refreshes grid.
- Bulk operations: select/deselect all; enter name + “Save” applies to selected faces (clears cluster_id); navigation prev/next cluster with wrap-around; names list sidebar updates after edits.
- Status/indicators show cluster position and counts; keyboard focus behavior (return to name input).

## Per-Person Analysis (Name Analysis tab)
- Names list with rename button; selecting name loads all faces with bboxes; right-click shows full image; delete face; double-click name to rename face.
- Timeline widget shows EXIF dates for selected name.
- Grid auto-calculates columns based on width; uses shared FaceImageWidget interactions (preview, delete, rename, accept predicted).

## Model Training (VGGFace tab, legacy)
- Stub UI; ModelManager loads various checkpoint types (simple ResNet18, FaceNet, VGG, ResNet50) with class mappings and accuracy; handles state_dict vs full-module checkpoints.

## Batch Recognition (Prediction tab)
- Runs in QThread; optional filter “only faces without manual name”.
- Shared preprocessing; writes predicted_name/confidence; updates histogram and name frequency table live; progress/cancel UX.
- Handles corrupt images gracefully; disables UI controls during run.

## Prediction Review (Review Predictions tab)
- Async data loader to avoid UI freeze; filters: by name, confidence range, unnamed only, prediction different from existing name; reload button.
- Grid lazy-renders visible items; all faces selected by default; single-click toggles selection, double-click accepts predicted name; inline edit of actual name; right-click preview with bbox overlay.
- Accept selected predictions in bulk; filter stats display; preserves selection state on scroll.

## Data Insights (Database Analysis tab)
- Stats: total faces, unique files/folders/names, faces with predictions, clusters, images without faces, duplicate filenames across subfolders.
- Clear database button (Detection tab) wipes images/faces/thumbnails/metadata respecting FK order.

## Cross-cutting Behavior
- Logging to `logs/face_recognition.log` + console; suppresses noisy libs.
- Caching: LRU caches for thumbnails and image details to reduce DB BLOB reads; async thumbnail loader for responsiveness.
- Schema constraints: UNIQUE on `(base_folder, sub_folder, filename)`; FK cascading for thumbnails/metadata; indexes on common lookups.
- Platform helpers for opening files/folders (per-OS).

## Cross-cutting Behavior
- Logging to `logs/face_recognition.log` plus console.
- All images/metadata/faces stored in SQLite (`faces.db`); thumbnails in BLOBs.
- Model artifacts in `face_recognition_models/`; YOLO weights `yolov11n-face.pt`.
