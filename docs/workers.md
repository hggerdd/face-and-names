# Face-and-Names v2 — Background Workers Contract

This document defines the job/executor contract for long-running tasks (ingest, clustering, batch prediction, repairs). It supports progress, cancellation, and resumability, keeping the PyQt UI responsive. Current implementation uses an in-process thread-pool `JobManager` with cooperative cancellation tokens and per-job checkpoints.

## Components
- **Job queue/registry**: holds enqueued jobs with metadata and current state (implemented by `JobManager`).
- **Executors**: bounded pool (default from config `workers.cpu_max`). Executors pull jobs FIFO today; priority lanes are planned.
- **Controller API**: enqueue, inspect, cancel, resume; emits progress events for UI. Retry hooks are planned.

## Job Model
- Fields: `id`, `type` (ingest/clustering/predict/repair/export/import), `priority` (high for user-triggered interactive), `payload` (job-specific options in JSON), `state` (queued/running/cancelled/completed/failed), `created_at`, `updated_at`, `started_at`, `finished_at`.
- Progress: counts and histograms relevant to job type, e.g.:
  - Ingest: files_total, files_done, faces_found, no_face_images, errors.
  - Clustering: faces_total, faces_done, clusters_created, noise_count, cluster_size_histogram.
  - Batch prediction: faces_total, faces_done, confidence_histogram, id_frequency.
- Checkpoints: resumable cursor stored per job; ingest currently publishes `next_index` checkpoints so the UI/job manager can resume without reprocessing completed items (FR-052/053).
- Errors: list with file/face references, error code, message, resolution (pending/skip/retry).
- Cancellation: cooperative cancellation token polled by workers; on cancel, job transitions to cancelled and retains partial progress (FR-009, FR-037).

## APIs (current/planned)
- `enqueue(job_type, payload, priority) -> job_id` (payload and checkpoint are optional)
- `inspect(job_id) -> state, progress, errors, checkpoint`
- `cancel(job_id)`
- `resume(job_id)` resumes from checkpoint if available.
- `retry(job_id, selection)` planned for failed items (ingest/predict/cluster) to honor retry/skip flows.

## Worker Responsibilities
- Acquire device handles once per batch (detector/model warm-up) to reduce reload overhead (FR-013, FR-061).
- Honor batching and min face size thresholds; record skip reasons in progress/errors (FR-062).
- Emit periodic progress events for UI and logs; flush checkpoints on intervals (ingest now emits checkpoints compatible with UI resume).
- Yield to higher-priority interactive tasks; avoid starving UI (FR-054).
- Respect config caps for CPU/GPU usage and memory where applicable (NFR-011).

## Logging/Audit Integration
- Jobs log lifecycle events (queued/start/finish/cancel) with durations and throughput.
- Errors are structured for diagnostics, with retry/skip decisions appended.
- Audit log updates for user-driven actions (accept/rename/delete/merge) occur at service layer, not in worker threads, but workers must surface the actions that require audit entries.

## Cancellation and Resume Semantics
- **Cancel**: stop after current batch, mark as cancelled, keep processed items.
- **Resume**: restart a new job that picks up pending items using stored checkpoints and error lists; don’t reprocess successful items (FR-053).

## UI Integration (PyQt)
- Workers emit signals or events received by the UI thread; no UI updates from worker threads.
- Progress surfaces include counts, histograms, and live stats consistent with requirements (FR-009, FR-021, FR-036).
