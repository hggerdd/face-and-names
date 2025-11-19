# Face-and-Names v2 – Service Contracts (Conceptual)

Informal interfaces for core services. These are language-agnostic shapes to guide implementation; actual classes/functions will be defined in code.

## IngestService
- `start_session(folders: list[str], options) -> session_id`  
  Options: recursive (bool), inline_prediction (bool), detector/predict thresholds, min_face_size, device preference.
- `resume_session(session_id)` resumes incomplete import.
- `cancel(session_id)` requests cancellation.
- `progress(session_id) -> ProgressSnapshot` with counts, faces/no-face, errors list.
- Responsibilities: folder selection scope enforcement (DB Root), EXIF orientation/metadata extraction, thumbnail generation, identity dedupe (content hash), detection, optional inline prediction, session tracking, retry/skip semantics, crash-resume using checkpoints.

## DetectorAdapter
- `warmup(device)`
- `detect(images: list[Image]) -> list[list[FaceDetection]]]` batched; must return bboxes (abs/rel), confidence, crops.
- Contracts: padded/clamped bboxes, reuse instance within batch; min face size enforcement recorded in metadata/errors.

## PredictionService
- Single entry point for inline and batch prediction.
- `predict_batch(faces: list[FaceRef], options) -> list[Prediction]]`  
  Options: device, batch_size, threshold, warmup, min_face_size.
- Must handle model-unavailable state gracefully; expose model metadata (name/version/device/default thresholds).

## ClusteringService
- `cluster(faces: list[FaceRef], algorithm, params, scope) -> ClusterResult`  
  Algorithms: DBSCAN, KMeans, Hierarchical; params per algorithm.  
  Scope: latest import, specific folders.
- Emits progress, noise count, cluster size distribution; supports cancel. Post-process to split oversized clusters and renumber sequentially; persists cluster IDs.

## FacesWorkspaceController
- Loads faces with filters (scope, confidence range, unnamed-only, differs-from-name, date range, groups).
- Provides selection model and bulk actions: accept prediction, rename, assign person (clears cluster), delete.
- Integrates with preview (full image + bbox) and overlay editor for drawing bboxes.

## PeopleService
- CRUD for person records (primary name, aliases, short names, birthdate, notes).
- Merge: consolidate person_ids; cascades to faces/images; resolves alias collisions.
- Group/Tag management: CRUD groups with hierarchy; assign multiple groups to a person; inheritance handling.

## ExportImportService
- Export: people/groups/person-group links, stats, optional faces summary to JSON/CSV; scoped to DB Root.
- Import: dry-run option; enforces unique primary names; prompts on alias collisions; dedupes via hashes; supports conflict resolution choices.

## DiagnosticsService
- Health checks: model presence/version, device availability, DB integrity, cache stats.
- Self-test: sample detection/prediction (pass/fail).
- Repair tools: rebuild thumbnails/crops; duplicate review (exact/near-duplicate) with resolution actions.

## Job/Worker Controller
- `enqueue(type, payload, priority) -> job_id`
- `inspect(job_id) -> state, progress, errors, checkpoint`
- `cancel(job_id)`, `resume(job_id)`, `retry(job_id, selection)`
- Emits events for UI; ensures priority lanes and yielding to interactive work.
