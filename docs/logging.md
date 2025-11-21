# Face-and-Names v2 – Logging & Observability Plan

## Goals
- Structured, consistent logs with rotation/retention (FR-051).
- Per-feature surfacing of recent errors in UI; support diagnostics and audit needs.
- Minimal PII; offline by default.

## Log Structure
- Format: JSON lines recommended; fields: `timestamp`, `level`, `logger`, `message`, `context` (job_id, image_id, face_id, file path relative), `module`, `exception` (if any).
- Levels: info/warn/error; debug optional via config.

## Rotation/Retention
- Default log path under DB Root (`logs/app.log`); rotate by size (default 5 MB) with limited history (default 3 files). Retention configurable via logging setup.

## Per-Feature Logging
- Ingest: session start/stop, throughput, skipped/failed files, retry/skip outcomes.
- Detection/Prediction: model/detector metadata (name/version/device), warm-up, batch sizes, failures with file/face refs.
- Clustering: algorithm/params, progress stats, cancel events, post-process results (cluster counts, noise).
- Export/Import: schemas used, dry-run results, conflicts and outcomes.
- Diagnostics: health check results, self-test outcomes.

## Audit Log (DB-backed)
- Stored in `audit_log` table (see schema). Records rename/merge/delete/accept-prediction actions with actor and details (BR-006).

## Metrics/Progress
- Progress events for background jobs include counts/histograms (faces processed, confidence distribution, cluster sizes) to feed UI.
- Throughput metrics for ingest, clustering, prediction; recorded in logs and surfaced in diagnostics.

## Error Handling
- Errors include code/category, user-facing message, and internal detail; retries/skip decisions appended.
- Missing models/detectors surfaced clearly; allow “model unavailable” state without crashing (FR-063).

## Privacy/Security
- No outbound logging by default; offline mode ensures logs stay local (NFR-014).
- Avoid raw PII beyond file paths and IDs; redact where possible.
