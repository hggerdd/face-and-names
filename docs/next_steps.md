# Next Iteration Checklist

Starting point for the rewrite (branch `rewrite/next-gen`).

## User Stories to Finalize
- Import photos from folder(s) (recursive optional), skip already-ingested, capture metadata, generate thumbnails, run detection, and optionally inline recognition; surface progress and allow cancel/resume.
- Browse images by folder; view metadata; see/edit face boxes; add manual annotations; delete faces; quick preview with bbox overlay.
- Cluster faces; filter by latest import/folders; adjust algorithm/params; save clusters; split/renumber; clear names/clusters.
- Review clusters to assign names; accept predicted names via double-click; bulk assign names to selected faces; delete faces; navigate clusters; keep names list updated.
- Analyze by person: list names, rename person globally, timeline by EXIF date, inspect/delete individual faces with preview.
- Batch recognition: run predictions (all or unnamed), update predicted_name/confidence, show histogram and name counts; cancelable.
- Prediction review: filter by name/confidence/unnamed/different, accept selected predictions in bulk, inline rename, lazy-load for performance.
- Data insights: show stats (faces, files, folders, names, predictions, clusters, duplicates, no-face images); allow full DB clear with confirmation.

## Performance & UX Targets (to decide)
- Startup target (e.g., <2s to main window/splash dismissal).
- Per-image ingest throughput (ms/image) with and without inline recognition.
- UI responsiveness ceiling (max acceptable stall in tabs).
- Background task pattern (shared worker/queue, progress/cancel contract, auto-refresh hooks).

## Interaction Rules to Lock
- Single vs double-click behaviors (select toggle vs accept predicted name).
- Delete semantics (per-face, confirmations, undo?).
- Preview behavior (right-click hold vs click, shared preview window).
- Standardized progress/cancel UI and disabled controls during long tasks.

## Data Contracts (defer until requirements locked)
- Schema for images/faces/metadata/clusters/predictions with explicit uniqueness, FKs, and indexes.
- Model artifact formats and validation (weights presence, device selection).
- Caching strategy (thumbnails/details) and eviction policy.

## Technical Decisions
- Core stack (likely PyQt + SQLite unless we upsize).
- Modularity: services vs UI; background workers; dependency boundaries to avoid heavy imports at startup.
- Testing approach: headless unit tests with stubs for CV/ML; regression smoke for schema creation and core flows.

## Risks / Open Questions
- Dataset size expectations → impacts schema and caching.
- Training in-app vs external; how models are supplied and validated.
- Resumable imports and duplicate handling strategy.
