# Face-and-Names – Target-State Specification (rewrite/next-gen)

All requirements are implementation-neutral, atomic, testable, and traceable to the consolidated source (“requirements.md”). “Source” tags: **[REQ]** denotes direct text from requirements.md; **[LEG]** denotes legacy behavior transformed into forward-looking requirements; **[DER]** denotes consolidation/interpretation.

## 1. Introduction and Scope
- The system ingests photos from a source-scoped datastore, detects and recognizes faces, clusters them, allows user-driven naming/verification, browsing/annotation, analysis, and diagnostics. It must support portable photo libraries (e.g., external drives) and remain responsive on modest hardware. **[REQ]**

## 2. Definitions and Glossary
- **DB Root**: Folder containing the database file; defines the scope of eligible images (DB root and all subfolders). **[REQ]**
- **Person ID**: Internal, stable identifier for a person; models operate on IDs (not names). **[REQ]**
- **People Record**: User-facing attributes for a Person ID (primary name, aliases/short names, optional birthdate, notes). **[REQ]**
- **Face Tile**: Reusable UI component showing a face crop, current name, predicted name + confidence, delete control, right-click preview. **[REQ]**
- **Prediction Service**: Shared pipeline for face preprocessing, model invocation, and thresholding. **[REQ]**
- **Image Identity**: Mechanism to uniquely identify an image independent of filename/location. **[REQ]**

## 3. Stakeholders and User Roles
- **End User**: Owns photo library; performs ingest, verification, naming, browsing, analysis.
- **System Maintainer**: Installs models, configures environment, inspects diagnostics.

## 4. Functional Requirements (FR)

### 4.1 Source Scoping and Ingest
- **FR-001** The system shall limit ingestion to images located in the DB Root and its subfolders only. **[REQ]**
- **FR-002** The system shall store all image paths relative to the DB Root to permit drive/mount changes without breaking references. **[REQ]**
- **FR-003** The system shall skip ingesting any image already present based on the image identity scheme (see Data Model). **[REQ]**
- **FR-004** The system shall support selecting one or more folders under the DB Root with a recursive option and per-subfolder checkboxes. **[REQ]**
- **FR-005** The system shall remember the last-used folder selection in a user config file. **[REQ]**
- **FR-071** The application shall allow choosing or creating the DB Root (SQLite file location) at runtime, treating that folder as the scope for ingest and relative paths. **[DER][USER]**
- **FR-072** Thumbnails generated during ingest shall be stored inside the SQLite database (BLOB) rather than the filesystem cache. **[DER][USER]**
- **FR-006** For each ingested image, the system shall correct EXIF-based orientation, extract EXIF/IPTC metadata, generate a JPEG thumbnail (≤ ~500px width), and persist these data. **[REQ][LEG]**
- **FR-007** The system shall track import sessions recording folder_count and incrementally recording image_count as images are processed. **[REQ]**
- **FR-008** The system shall record images with zero detected faces while still storing their thumbnails and metadata. **[REQ][LEG]**
- **FR-009** The system shall provide ingest progress (file/folder counts, faces, no-face images) and support cancellation. **[REQ]**

### 4.2 Detection and Recognition
- **FR-010** The system shall detect faces in each image using a detector that supports padded, clamped bounding boxes, storing both absolute and relative coordinates. **[REQ][LEG]**
- **FR-011** The system shall save face crops as JPEG and link them to their source image. **[REQ][LEG]**
- **FR-012** The system shall optionally run inline recognition via the shared prediction service during ingest and persist predicted person ID and confidence when above a configurable threshold. **[REQ][LEG]**
- **FR-013** The system shall reuse detector/model instances within a batch to minimize reload overhead. **[REQ]**

### 4.3 Browsing and Annotation
- **FR-014** The system shall present a folder/image tree (from DB) with previous/next navigation and a metadata table for the selected image. **[REQ][LEG]**
- **FR-015** The system shall overlay stored face boxes on images and allow users to draw and save new face boxes with an assigned person ID/name. **[REQ][LEG]**
- **FR-016** The system shall allow per-face rename and delete actions via the face tile; deletions remove the face record. **[REQ][LEG]**
- **FR-017** On right-click of a face tile, the system shall show a full-image preview with a red bounding box and labels (current and/or predicted) using a shared preview window. **[REQ][LEG]**

### 4.4 Clustering
- **FR-018** The system shall load faces for clustering filtered by “latest import only” and/or selected folders. **[REQ]**
- **FR-019** The system shall support clustering algorithms (DBSCAN, KMeans, Hierarchical) with user-adjustable parameters and selectable face-recognition backbone. **[REQ]**
- **FR-020** The system shall assign cluster IDs to faces, persist them, and post-process to split oversized clusters and renumber sequentially (handling noise explicitly). **[REQ]**
- **FR-021** The system shall provide clustering progress and statistics (e.g., noise count, cluster size distribution) with cancellation. **[REQ]**
- **FR-022** The system shall allow clearing all names and/or cluster assignments in bulk. **[REQ]**

### 4.5 Cluster Review & Naming
- **FR-023** The Naming view shall display faces in clusters using the shared face tile. **[REQ]**
- **FR-024** Single-click on a face tile shall toggle selection state; inactive faces are visually distinct. **[REQ][LEG]**
- **FR-025** Double-click on a face image shall accept the predicted person ID/name for that face. **[REQ][LEG]**
- **FR-026** Double-click on a face name shall open a rename dialog for that face. **[REQ][LEG]**
- **FR-027** Users shall be able to bulk-assign a name/person ID to all selected faces in the current cluster, clearing their cluster IDs. **[REQ]**
- **FR-028** The system shall support select-all/deselect-all in the current cluster and wrap-around navigation between clusters with a position indicator. **[REQ]**
- **FR-029** Deleting a face from the Naming view shall remove it from the DB and refresh the cluster display. **[REQ][LEG]**

### 4.6 Per-Person Analysis
- **FR-030** The system shall list people (Person IDs) with their primary names/aliases and support global rename operations across all linked faces. **[REQ]**
- **FR-031** Selecting a person shall show all their faces (with bboxes) and allow per-face delete and rename via face tile conventions. **[REQ]**
- **FR-032** The system shall display a timeline of EXIF capture dates for the selected person. **[REQ]**
- **FR-033** The system shall optionally display/computed age-at-capture when birthdate is present. **[REQ]**

### 4.7 Batch Recognition
- **FR-034** The system shall run batch prediction via the shared prediction service over (a) all faces or (b) only faces without manual names. **[REQ]**
- **FR-035** The system shall update predicted person ID and confidence for each processed face. **[REQ]**
- **FR-036** The system shall provide live confidence histogram and predicted ID/name frequency updates during batch processing. **[REQ]**
- **FR-037** The system shall support canceling batch prediction and leave already-processed results intact. **[REQ]**

### 4.8 Prediction Review
- **FR-038** The system shall load prediction data asynchronously to avoid UI blocking. **[REQ]**
- **FR-039** The system shall offer filters: name/alias substring, confidence min/max, unnamed-only, and “prediction differs from existing name.” **[REQ]**
- **FR-040** The review grid shall be virtualized and use shared face tiles; all faces selected by default; single-click toggles selection; double-click accepts prediction; inline rename; right-click preview. **[REQ][LEG]**
- **FR-041** The system shall allow bulk acceptance of predictions for selected faces. **[REQ]**
- **FR-042** The system shall display filter statistics and offer a reload action. **[REQ]**

### 4.9 Data Insights
- **FR-043** The system shall present statistics: total faces, unique files/folders/names, faces with predictions, clusters, images without faces, duplicates across subfolders. **[REQ]**
- **FR-044** The system shall provide a DB-clear action (scoped to this DB) that deletes images/faces/thumbnails/metadata in FK-safe order with confirmation. **[REQ]**

### 4.10 People Management
- **FR-045** The system shall provide a dedicated People Management page for CRUD on Person IDs, including primary name, aliases/short names, optional birthdate, and notes. **[REQ]**
- **FR-046** The system shall support merging two or more Person IDs into one, updating all linked faces/images. **[REQ]**
- **FR-047** Updating a person’s display name or aliases shall not require model retraining; model outputs remain Person IDs. **[REQ]**
- **FR-068** The People Management page shall support CRUD for reusable groups/tags (e.g., Family, Study Friends) and assign multiple groups to each Person ID. **[DER]**
- **FR-069** The system shall support hierarchical groups (parent/child) such that a parent group (e.g., Family) can contain subgroups (e.g., Near Family, Extended Family), and membership in a child implies membership in its parent. **[DER]**
- **FR-070** The Faces workspace filters shall include group/tag selection (multi-select) to scope faces by group membership. **[DER]**

### 4.11 Diagnostics
- **FR-048** The system shall present a diagnostics panel showing model presence/health, DB health, cache stats, and device selection (CPU/GPU). **[REQ]**
- **FR-049** The system shall surface clear errors for missing models or corrupt images and allow skip/retry options with logging. **[REQ]**
- **FR-050** The system shall provide tools to repair missing thumbnails and to review duplicates detected by the identity scheme. **[REQ]**

### 4.12 Resilience, Logging, and Recovery
- **FR-051** The system shall emit structured logs with levels (info/warn/error), rotation/retention, and per-feature surfaces for recent errors; logs shall record retry/skip outcomes. **[DER]**
- **FR-052** The system shall support retry/skip workflows for failed items in ingest, detection, prediction, and clustering while preserving partial progress after cancellation. **[DER]**
- **FR-053** The system shall resume an interrupted ingest (cancel/crash) using recorded import session state to avoid reprocessing completed items. **[DER]**
- **FR-054** The system shall cap background worker concurrency and prioritize interactive tasks so heavy jobs do not starve the UI or each other. **[DER]**

### 4.13 Export and Portability
- **FR-055** The system shall export/import people records (names/aliases/birthdates/notes) and faces/stats summaries to portable formats (e.g., JSON/CSV) scoped to a DB Root. **[DER]**
- **FR-056** A DB Root (database + images) shall remain portable across machines; on path/mount changes the app shall detect and relink automatically when relative structure matches. **[DER]**
- **FR-057** The system shall provide a built-in environment self-test covering model presence, device availability, and sample detection/prediction with clear pass/fail output. **[DER]**

### 4.14 Identity Scheme
- **FR-058** The system shall store both a strong content hash and a perceptual hash per image and use them to detect duplicates and moved/renamed files under the DB Root. **[DER]**
- **FR-059** Identity collisions (different files with same hash) shall surface a conflict workflow (keep existing, replace, or mark duplicate) and log the decision. **[DER]**

### 4.15 Prediction/Detection Pipeline Controls
- **FR-060** The prediction service shall support device selection (CPU/GPU) with automatic fallback and per-model default thresholds. **[DER]**
- **FR-061** The detector and recognition stages shall support configurable batching/warm-up within a session to reduce reload/latency overhead. **[DER]**
- **FR-062** The system shall enforce a minimum face size threshold (configurable) with clamp/skip behavior recorded in metadata when faces are below the threshold. **[DER]**
- **FR-063** The absence of a recognition model shall not break ingest, detection, clustering, or UI flows; the system shall surface a clear “model unavailable/untrained” state and allow later installation/training without data loss. **[DER]**

### 4.16 Unified Faces Workspace
- **FR-064** The application shall provide a single “Faces” workspace that replaces separate cluster/prediction/person tabs; it shall surface shared filters (scope, confidence range, unnamed-only, differs-from-name, date range) and mode toggles (Cluster, Prediction, Person, All). **[DER]**
- **FR-065** The Faces workspace shall display a virtualized grid of face tiles showing current name (if any), predicted name + confidence, and cluster ID badge, with shared interactions: single-click toggles selection, double-click accepts prediction or opens rename depending on mode, right-click opens preview. **[DER]**
- **FR-066** The Faces workspace shall include a contextual side panel that changes with mode: Cluster mode shows cluster navigation/histogram and bulk assign/clear; Prediction mode shows confidence histogram and bulk accept/rename; Person mode shows person metadata/timeline and bulk rename/merge; All mode shows summary stats. **[DER]**
- **FR-067** The Faces workspace shall expose global actions in a footer/header for start/stop clustering, start/stop batch prediction, progress indicators, and status of model availability/device selection, without requiring navigation to another tab. **[DER]**

## 5. Non-Functional Requirements (NFR)
- **NFR-001 Performance**: Time from launch to main UI ready (or splash dismissal) shall be ≤ 2 seconds on target modest hardware, measured with a representative DB and no blocking tasks. **[REQ]**
- **NFR-002 Performance**: Tab change shall not trigger heavy processing; feature-specific heavy work shall start only when the feature is invoked. **[REQ]**
- **NFR-003 Responsiveness**: All long-running operations shall run in background workers and expose progress and cancellation; the UI thread shall remain responsive. **[REQ]**
- **NFR-004 Portability**: Moving the DB Root (e.g., different drive letter) shall not break image references when the relative structure is preserved. **[REQ]**
- **NFR-005 Consistency**: A single face tile implementation and a single prediction service implementation shall be used across all views. **[REQ]**
- **NFR-006 UX Consistency**: All labels/tooltips shall be descriptive (e.g., “Face recognition confidence” instead of generic “confidence”) and follow a consistent style guide (typography, spacing, buttons, panels). **[REQ]**
- **NFR-007 Extensibility**: The system shall support pluggable recognition models via a defined runner interface without requiring UI rewrites. **[REQ]**
- **NFR-008 Reliability**: Identity scheme shall prevent duplicate ingest of the same image content even if filenames/paths change under the DB Root. **[REQ]**
- **NFR-009 Testability**: Each requirement shall be verifiable via functional tests (FRs) or performance/reliability tests (NFRs) with measurable criteria as stated. **[DER]**
- **NFR-010 Performance**: Ingest, clustering, and batch prediction shall meet agreed throughput targets and publish measured rates; performance tests shall enforce these budgets on target hardware. **[DER]**
- **NFR-011 Resource Use**: Background jobs shall honor RAM/GPU ceilings (to be agreed) and degrade gracefully rather than exhaust system resources. **[DER]**
- **NFR-012 Storage**: Thumbnails and face crops shall stay within defined footprint budgets (e.g., ≤ X GB per 10k images) while meeting quality needs. **[DER]**
- **NFR-013 Accessibility**: The UI shall support keyboard navigation (including accept/rename/delete shortcuts), focus order, screen-reader labels, and contrast targets aligned to WCAG 2.1 AA. **[DER]**
- **NFR-014 Security/Privacy**: Processing shall be local by default with no outbound network calls unless configured; optional encryption for the database and stored thumbnails/crops shall be available. **[DER]**
- **NFR-015 UI Performance**: Views that list many faces or images (e.g., naming, per-person, people list) shall use virtualization or pagination to maintain responsiveness and memory bounds. **[DER]**

## 6. Business Rules
- **BR-001** Person IDs are the only identifiers used by models; user-visible names/aliases are resolved at presentation time. **[REQ]**
- **BR-002** Changing a person’s display name or aliases does not alter model outputs; accepted predictions rebind faces to Person IDs, not names. **[REQ]**
- **BR-003** Images outside the DB Root are out of scope and must not be ingested or displayed. **[REQ]**
- **BR-004** Duplicate detection uses the chosen image identity scheme; duplicates are not re-ingested. **[REQ]**
- **BR-005** Primary names shall be unique per DB Root; alias collisions shall prompt user resolution, and merges shall preserve or reconcile aliases. **[DER]**
- **BR-006** Rename/merge/delete/accept-prediction actions shall be audit logged with timestamp and actor to support traceability. **[DER]**
- **BR-007** Person IDs may belong to multiple groups/tags simultaneously; group hierarchy implies inheritance of membership from child to parent. **[DER]**

## 7. Data / Information Model (Conceptual)
- **Image**: relative_path, sub_folder, filename, identity (hash/perceptual), dimensions/size, import_id, has_faces, thumbnail BLOB, metadata entries. **[REQ]**
- **Face**: image_id, face_crop BLOB, bbox_abs, bbox_rel, cluster_id, person_id (nullable), predicted_person_id (nullable), prediction_confidence (nullable), provenance (manual/predicted). **[REQ]**
- **Import Session**: import_id, import_date, folder_count, image_count. **[REQ]**
- **Metadata**: image_id, key, type (EXIF/IPTC), value. **[REQ]**
- **Person**: person_id, primary_name, aliases/short_names, birthdate (optional), notes. **[REQ]**
- **Group**: group_id, name, parent_group_id (nullable), description/tag color. **[DER]**
- **PersonGroup**: person_id, group_id (many-to-many). **[DER]**
- **Stats**: computed aggregates for Data Insights. **[REQ]**

## 8. Process Descriptions / User Flows (High-Level)
- **Ingest Flow**: User selects folders → system records import session → for each image: identity check → metadata/orientation/thumbnail → detection → optional inline prediction → persist results → progress with cancel. **[REQ]**
- **Clustering Flow**: User selects scope + algorithm → background clustering → stats/progress → cluster IDs saved → post-process split/renumber. **[REQ]**
- **Naming Flow**: User navigates clusters → selects faces (toggle) → accepts predictions (double-click) or bulk-assigns names → faces rebound to Person IDs, clusters cleared → navigation with indicators. **[REQ]**
- **Prediction Flow**: User starts batch prediction → background processing via shared prediction service → updates predicted IDs/confidences → histogram/name freq shown live → cancel supported. **[REQ]**
- **Prediction Review Flow**: Async load → apply filters → virtualized grid → accept/rename/delete via face tile → bulk accept → reload. **[REQ]**
- **People Management Flow**: CRUD + merge on Person IDs; edit names/aliases/birthdate/notes; updates cascade to linked faces. **[REQ]**
- **Diagnostics Flow**: User opens diagnostics → sees model/DB/cache/device health → resolves missing assets/errors; tools for thumbnail/duplicate repair. **[REQ]**

## 9. Interfaces and Integration Points
- **Model Runner Interface**: Accepts preprocessed face tensor; returns embeddings or predicted Person ID + confidence; exposes metadata (name, version, device, thresholds). **[REQ]**
- **Prediction Service API**: Single entry point for inline and batch prediction; configurable thresholds; returns predicted Person ID + confidence. **[REQ]**
- **Detector Interface**: Accepts image; returns faces with padded/clamped bboxes and crops. **[REQ]**

## 10. Constraints and Assumptions
- UI technology and storage can be chosen freely, provided functional and non-functional requirements are met. **[DER]**
- Performance targets assume “modest hardware” (to be profiled and agreed during planning). **[REQ]**
- The DB Root will contain both the database file and the image hierarchy. **[REQ]**
- The supported image formats (e.g., JPEG/PNG/HEIC) and max resolution/min face size shall be agreed; RAW formats are out of scope unless explicitly added. **[DER]**
- Multiple DB Roots may coexist; operations (ingest, clear, export) are scoped to the currently selected DB Root. **[DER]**

## 11. Open Issues / Items Requiring Clarification
- **OI-001** Exact hash/identity scheme selection (content hash vs perceptual hash vs hybrid) needs final decision and collision/robustness criteria. **[REQ]**
- **OI-002** Precise performance budgets for ingest throughput, clustering, and batch prediction on target hardware need quantification. **[REQ]**
- **OI-003** Training workflow (in-app vs external) and how trained models are delivered/validated remain to be defined. **[REQ]**
- **OI-004** Age-at-capture display rules (format, fallback when capture date missing) need definition. **[REQ]**
- **OI-005** Duplicate/repair tools UX (approval flow, conflict resolution) needs detailed design. **[REQ]**
- **OI-006** Accessibility/theming scope (which controls, required contrasts, keyboard shortcuts) needs specification. **[REQ]**
- **OI-007** Specific concurrency caps and prioritization rules for background tasks vs UI responsiveness need agreement. **[DER]**
- **OI-008** Export/import format details (fields, redaction of PII, conflict resolution) need specification. **[DER]**
- **OI-009** Security posture: default network isolation vs optional online features, and key management for optional encryption, need definition. **[DER]**
