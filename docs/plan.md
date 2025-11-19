# Face-and-Names v2 – Implementation Plan

This plan derives from `docs/requirements.md` and defines milestones, scope, and deliverables. No code is produced here; it establishes what to build and in what order. All IDs refer to `docs/requirements.md`.

## Guiding Constraints
- Language/runtime: Python; dependency/env management via `uv` (no pip).
- Style: PEP 8; avoid inventing features beyond stated requirements; no personal data storage; no unsolicited backend boilerplate.
- Offline by default; optional encryption and network features must be explicit.

## Milestones

### 1) Foundations & Architecture
- Requirements coverage: FR-001..009, NFR-001..009, BR-001..004, OI-001/002/007.
- Deliverables:
  - Architecture document: app layout, service boundaries, background worker model (queues, progress, cancel, resume), device abstraction, UI/worker separation.
  - Identity scheme decision: content hash algorithm + perceptual hash and collision handling workflow (FR-003, FR-058/059, BR-004).
  - Config model: global vs DB-scoped settings (e.g., last folder selection, thresholds, device choice) with file formats/paths.
  - Performance budgets: startup (≤2s), ingest/clustering/prediction throughput targets on modest hardware; concurrency caps and prioritization rules (NFR-001/003/010, OI-002/007).

### 2) Schema & Storage
- Requirements coverage: Data Model, FR-007/008/020/022/044/058/059, NFR-004/012/014.
- Deliverables:
  - DB schema DDL: Image, Face, ImportSession, Metadata, Person, Group, PersonGroup, Stats tables; constraints and indexes.
  - Storage strategy: thumbnails and face crops (BLOB vs files), size/quality targets (NFR-012), FK-safe clear/reset (FR-044).
  - Portability rules: relative paths rooted at DB Root, relink behavior on mount changes (FR-002, NFR-004).
  - Optional encryption hooks for DB and media (NFR-014).

### 3) Model & Prediction Services
- Requirements coverage: FR-010..013, FR-034..037, FR-060..063, NFR-005/007, OI-003.
- Deliverables:
  - Detector interface spec: inputs, padded/clamped bboxes, absolute/relative coords; batch reuse (FR-010/013).
  - Prediction service API: single entry for inline and batch prediction; thresholds; device selection/fallback; min face size policy (FR-012, FR-034..037, FR-060..062).
  - Model runner plugin contract: metadata (name/version/device), warm-up, batching, absence handling (FR-063).
  - Sample model validation checklist and health checks.

### 4) Ingest Pipeline
- Requirements coverage: FR-001..009, FR-011..013, FR-051..054, FR-062/063.
- Deliverables:
  - Flow spec: folder selection (per-subfolder checkboxes, recursive, remember last), session tracking (folder_count, image_count), identity dedupe (FR-003).
  - Processing steps: EXIF orientation, EXIF/IPTC extraction, thumbnail generation (≤~500px), detection, optional inline prediction, zero-face handling (FR-006..009, FR-011/012).
  - Control surface: progress metrics, cancel, retry/skip, crash-resume semantics using session state (FR-009, FR-051..053).
  - Logging contract for ingest events and errors.

### 5) Clustering & Post-Processing
- Requirements coverage: FR-018..022, FR-054, FR-060..062.
- Deliverables:
  - Algorithm options and parameters: DBSCAN, KMeans, Hierarchical; scope filters (latest import/folders).
  - Progress and cancellation API; metrics (noise count, cluster size distribution).
  - Post-process rules: split oversized clusters and renumber sequentially; noise handling.
  - Configuration defaults and resource caps.

### 6) Faces Workspace & UI Patterns
- Requirements coverage: FR-014..017, FR-023..029, FR-038..042, FR-064..067, NFR-003/006/013/015, BR-001/002/006/007.
- Deliverables:
  - Unified face tile spec: displayed labels (name, predicted name+confidence, cluster badge), interactions (single/double/right-click, delete), preview behavior.
  - Faces workspace modes: Cluster, Prediction, Person, All; shared filters (scope, confidence range, unnamed-only, differs-from-name, date range).
  - Virtualization/pagination plan for large grids (NFR-015).
  - Accessibility/keyboard interactions: focus order, shortcuts (accept/rename/delete), screen reader labels (NFR-013).
  - Image view overlays: stored bboxes, draw/save new bboxes with person assignment (FR-014..017).

### 7) People & Groups Management
- Requirements coverage: FR-030..033, FR-045..047, FR-068..070, BR-005/006/007.
- Deliverables:
  - People CRUD flows: primary name, aliases/short names, birthdate (optional), notes; uniqueness and alias collision handling.
  - Merge behavior: cascading updates to linked faces/images; audit logging.
  - Groups/tags: hierarchy, membership inheritance, multi-select filters in faces workspace (FR-070).
  - Global rename operations and effect on model outputs (BR-001/002).

### 8) Naming & Prediction Review Flows
- Requirements coverage: FR-023..029, FR-034..037, FR-038..042.
- Deliverables:
  - Naming view: cluster navigation, select-all/deselect-all, wrap-around navigation, bulk assign name/person ID (clears cluster IDs), delete actions (refresh clusters).
  - Prediction review: async load, filters (name/alias substring, confidence min/max, unnamed-only, prediction-differs), virtualized grid; bulk accept/rename/delete.
  - Live stats: confidence histogram, predicted ID/name frequencies during batch processing.
  - Interaction rules: single-click toggles selection (inactive faces distinct), double-click accepts prediction or opens rename, right-click preview.

### 9) Diagnostics & Recovery
- Requirements coverage: FR-048..054, FR-055..057, FR-060..063, NFR-008/011/014.
- Deliverables:
  - Diagnostics panel contents: model presence/health, DB health, cache stats, device selection.
  - Error surfacing: missing models/corrupt images; skip/retry controls with logging.
  - Repair tools: rebuild thumbnails, duplicate review driven by identity scheme (FR-050).
  - Environment self-test: model presence, device availability, sample detection/prediction with clear pass/fail (FR-057).

### 10) Export/Import & Portability
- Requirements coverage: FR-055..057, FR-058/059, NFR-004/014, BR-003/004.
- Deliverables:
  - JSON/CSV schemas for people records (names/aliases/birthdates/notes), groups, and faces/stats summaries scoped to DB Root.
  - Import rules: conflict resolution, alias collisions, duplicate detection.
  - Relink algorithm for moved DB Root with same relative structure; detection of moved/renamed files using hashes.
  - Privacy posture and optional encryption for exported data.

### 11) Testing & Observability
- Requirements coverage: NFR-009/010/011/012/015, BR-006.
- Deliverables:
  - Test matrix mapped to requirement IDs (functional, performance, resilience, accessibility).
  - Performance tests: startup time, ingest throughput, clustering/prediction rates; resource ceilings (RAM/GPU) and degradation behavior.
  - Resilience tests: cancel/resume for ingest/clustering/prediction; identity collision handling.
  - Logging/metrics spec: structured logs with rotation/retention, audit fields for rename/merge/delete/accept; progress metrics for background jobs.

## Execution Order (High-Level)
1) Foundations & Architecture; Schema & Storage; Model/Prediction contracts.
2) Ingest pipeline (headless) with progress/cancel/resume and logging/retry; finalize SQLite DDL/bbox/alias handling.
3) Clustering module with post-processing and stats.
4) Faces workspace patterns, tiles, previews, overlays (PyQt layout matching `docs/ui_wireframes.md`).
5) Naming and prediction review flows with batch prediction.
6) People/Groups management, rename/merge, audit logging.
7) Diagnostics/Recovery and environment self-test.
8) Export/Import and portability/relink tools.
9) Performance/accessibility hardening and full test suite; lock dependency versions in `pyproject.toml` and `uv.lock`.

## Open Issues to Resolve Early
- OI-001: Identity scheme details and collision policy. Proposal: compute strong content hash (SHA-256) over normalized image bytes (after EXIF orientation) plus a 64-bit perceptual hash (e.g., pHash) on the thumbnail-ready image. Use SHA-256 as primary dedupe/relink key; use perceptual hash to surface near-duplicates. Collision handling: if SHA-256 matches and perceptual hash distance is small, treat as same image; if SHA matches but path differs, log as move/rename; if only perceptual hash matches, flag for user decision and keep both. Record decisions in audit log.
- OI-002: Precise ingest/clustering/prediction performance budgets for target hardware. Draft targets: startup ≤2s with representative DB; ingest ≥3–5 img/s without detection, ≥1–2 img/s with detection+inline prediction on modest CPU; clustering 10k faces <2 min; batch prediction ≥10 faces/s CPU, ≥30 faces/s GPU. Finalize after profiling on agreed hardware.
- OI-003: Training/model delivery/validation workflow. Proposal: define model slots and runner contract; allow drop-in runners; validate via version check plus sample detection/prediction self-test (FR-057); if model absent, run in “model unavailable” state per FR-063 with clear UI affordance.
- OI-004: Age-at-capture rules. Proposal: use EXIF capture date when available; if missing, show “unknown.” When birthdate exists, display age floored to years with tooltip for exact date range; hide age when data is incomplete.
- OI-005: Duplicate/repair tools UX. Proposal: “Duplicates” panel showing exact matches (SHA-256) in different paths and near-duplicates by perceptual hash distance. Actions: keep existing, replace, or mark duplicate; log decision. Repair tools rebuild thumbnails/crops and retry failed ingest entries with skip/retry controls.
- OI-007: Concurrency caps and prioritization rules. Proposal: small default worker pool (e.g., 2–4 CPU workers, 1 GPU slot); interactive tasks preempt heavy jobs; background jobs yield periodically; configurable caps per device; batching/warm-up to reduce reload overhead.
- OI-008: Export/import field definitions, PII handling. Proposal: export people (person_id, primary name, aliases, birthdate?, notes), groups (id/name/parent), person-group links, faces/folder stats (counts, cluster IDs, predicted IDs/confidence optional). Import enforces unique primary names, prompts on alias collisions, dedupes via hashes; support dry-run. Minimize PII to required fields only.
- OI-009: Security posture. Proposal: offline by default; no outbound calls unless user opts in. Optional encryption for DB/thumbnails/crops and exported archives. Audit log rename/merge/delete/accept with timestamps; avoid storing extra personal data.
